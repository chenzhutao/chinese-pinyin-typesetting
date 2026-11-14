# -*- coding: utf-8 -*-
"""用本机 Chrome/Edge 无头模式对生成的 HTML 做排版体检。

检查项（注入 JS，在页面加载时执行，结果写回 DOM，用 --dump-dom 读出）：
1. 桌面 1000px / 手机 390px 两个视口宽度下均无水平溢出；
2. 拼音（rt）未超出注音单元（无截断）；
3. 同一诗句 .v 内各汉字底部基线一致（误差 <1.5px）；
4. 诗句 .v 未发生句中折行（高度 ≈ 单行）；
5. 拼音声调符号确实存在（ā á ǎ à …）；
6. 行首无标点（，。、；：！？）。

用法：python tests/browser_check.py a.html b.html …（无 Chrome 时输出 skip 并退出 0）
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

_INJECT = r"""
(function () {
  var out = {uri: location.href, overflows: [], truncated: 0, baselineBad: [],
             wrapped: [], tones: 0, punctLineStart: false, rtCount: 0, centerBad: 0,
             paraPunctStart: [], paraPunctEnd: [], indentBad: [], brokenClusters: []};
  var OPEN_RE = /[（〔【｛《〈「『“‘(\[{<«]/;
  var CLOSE_LINE_START = /^[，。、；：！？）」』》”’…—～~%）]}»]/;
  var de = document.documentElement;
  out.viewport = window.innerWidth + 'x' + window.innerHeight;
  out.scroll = {sw: de.scrollWidth, cw: de.clientWidth};
  if (de.scrollWidth > de.clientWidth + 1) out.overflows.push('doc');
  document.querySelectorAll('.sheet').forEach(function (s) {
    if (s.scrollWidth > s.clientWidth + 1) out.overflows.push('sheet');
  });
  document.querySelectorAll('.stanza, .para').forEach(function (s) {
    if (s.scrollWidth > s.clientWidth + 1) out.overflows.push('block:' + s.className);
  });
  out.noToneMode = document.body.classList.contains('mode-blank_pinyin')
    || document.body.classList.contains('mode-hanzi');
  var toneRe = /[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜńňǹ]/;
  out.centerBad = 0;
  document.querySelectorAll('.c').forEach(function (c) {
    var rt = c.querySelector('rt.y'), h = c.querySelector('.h, .tz');
    if (rt && h && rt.textContent.trim()) {
      var a = rt.getBoundingClientRect(), b = h.getBoundingClientRect();
      if (Math.abs((a.left + a.right) / 2 - (b.left + b.right) / 2) > 1.2) out.centerBad++;
    }
  });
  document.querySelectorAll('rt.y').forEach(function (rt) {
    out.rtCount++;
    if (toneRe.test(rt.textContent)) out.tones++;
    var ruby = rt.closest('.c');
    if (ruby && rt.scrollWidth > ruby.clientWidth + 2) out.truncated++;
  });
  document.querySelectorAll('.v').forEach(function (v, i) {
    var hs = v.querySelectorAll(':scope > ruby > .h, :scope > .nb ruby .h');
    var bottoms = [];
    hs.forEach(function (h) { bottoms.push(h.getBoundingClientRect().bottom); });
    if (bottoms.length > 1) {
      var mn = Math.min.apply(null, bottoms), mx = Math.max.apply(null, bottoms);
      if (mx - mn > 1.5) out.baselineBad.push({v: i, delta: +(mx - mn).toFixed(2)});
    }
    var cellEl = v.querySelector('ruby');
    var cellH = cellEl ? cellEl.getBoundingClientRect().height : 0;
    if (cellH > 0 && v.getBoundingClientRect().height > cellH * 2.2)
      out.wrapped.push(i);
    var fr = v.querySelector('ruby');
    if (fr && fr.classList.contains('p') &&
        CLOSE_LINE_START.test(fr.textContent)) out.punctLineStart = true;
  });
  // ---- 流式正文（.para）：避头尾 / 首行缩进 / 簇完整性 -------------------
  document.querySelectorAll('.para').forEach(function (p, pi) {
    var cs = getComputedStyle(p);
    var pr = p.getBoundingClientRect();
    var pl = pr.left + parseFloat(cs.paddingLeft || 0);
    var right = pr.right - parseFloat(cs.paddingRight || 0);
    p.querySelectorAll('ruby.c.p').forEach(function (r) {
      var rr = r.getBoundingClientRect(), t = r.textContent.trim();
      // 行首禁排：非开启类标点出现在行首（首行缩进后的首格除外）
      if (rr.left - pl < 2.5 && !OPEN_RE.test(t))
        out.paraPunctStart.push({p: pi + 1, ch: t});
      // 行尾禁排：开启类标点落在行尾
      if (OPEN_RE.test(t) && Math.abs(rr.right - right) < 2.5)
        out.paraPunctEnd.push({p: pi + 1, ch: t});
    });
    var first = p.querySelector('ruby');
    if (first) {
      var cw = first.getBoundingClientRect().width;
      var got = first.getBoundingClientRect().left - pl;
      if (Math.abs(got - cw * 2) > 2.5)
        out.indentBad.push({p: pi + 1, got: +got.toFixed(1), want: +(cw * 2).toFixed(1)});
    }
  });
  // 簇完整性：.nb 内所有注音单元必须在同一行（同断行组）
  document.querySelectorAll('.nb').forEach(function (nb, i) {
    var bottoms = [];
    nb.querySelectorAll('ruby').forEach(function (r) {
      bottoms.push(r.getBoundingClientRect().bottom);
    });
    if (bottoms.length > 1 &&
        Math.max.apply(null, bottoms) - Math.min.apply(null, bottoms) > 2)
      out.brokenClusters.push(i);
  });
  var pre = document.createElement('pre');
  pre.id = 'cpt-check';
  pre.textContent = JSON.stringify(out);
  document.body.appendChild(pre);
})();
"""


def find_browser() -> str | None:
    for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(env, "")
        for sub, exe in (("Google/Chrome/Application", "chrome.exe"),
                         ("Microsoft/Edge/Application", "msedge.exe"),
                         ("Chromium/Application", "chrome.exe")):
            p = Path(base) / sub / exe
            if p.is_file():
                return str(p)
    from shutil import which
    return which("chrome") or which("msedge") or which("chromium")


def run_check(exe: str, html: Path, width: int, height: int = 1400) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="cpt_check_"))
    wrapped = tmp / (html.stem + f"_w{width}.html")
    src = html.read_text(encoding="utf-8")
    # headless Chrome 将 innerWidth 钳到 ≥500；目标宽度更窄时强制 .sheet
    # 内容宽，以真实触发窄屏折行（手机阅读的实际风险场景）。
    if width < 500:
        src = src.replace(
            "</head>",
            f'<style>.sheet{{max-width:{width - 20}px !important;'
            f'margin:0 auto !important}}</style></head>')
    wrapped.write_text(src.replace("</body>", f"<script>{_INJECT}</script></body>"),
                       encoding="utf-8")
    cmd = [exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
           f"--window-size={width},{height}", "--dump-dom",
           wrapped.resolve().as_uri()]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=90,
                       encoding="utf-8", errors="replace")
    m = re.search(r'<pre id="cpt-check">(.*?)</pre>', r.stdout, re.S)
    if not m:
        return {"file": html.name, "viewport": f"{width}px", "error":
                f"no-check-output rc={r.returncode} {(r.stderr or '')[:120]}"}
    data = json.loads(m.group(1))
    data["file"] = html.name
    return data


def verdict(d: dict) -> list[str]:
    problems = []
    if "error" in d:
        return [d["error"]]
    if d.get("overflows"):
        problems.append(f"水平溢出: {d['overflows'][:3]}")
    if d.get("truncated"):
        problems.append(f"{d['truncated']} 个拼音可能被截断")
    if d.get("baselineBad"):
        problems.append(f"基线不齐: {d['baselineBad'][:3]}")
    if d.get("wrapped"):
        problems.append(f"诗句折行: 行号 {d['wrapped'][:5]}")
    if d.get("punctLineStart"):
        problems.append("标点出现在行首")
    if d.get("paraPunctStart"):
        problems.append(f"段落行首禁排标点 {len(d['paraPunctStart'])} 处: "
                        + ", ".join(f"第{x['p']}段“{x['ch']}”" for x in d['paraPunctStart'][:4]))
    if d.get("paraPunctEnd"):
        problems.append(f"段落行尾开启标点 {len(d['paraPunctEnd'])} 处: "
                        + ", ".join(f"第{x['p']}段“{x['ch']}”" for x in d['paraPunctEnd'][:4]))
    if d.get("indentBad"):
        problems.append(f"首行缩进≠2字宽 {len(d['indentBad'])} 段: {d['indentBad'][:3]}")
    if d.get("brokenClusters"):
        problems.append(f"{len(d['brokenClusters'])} 个断行簇被拆行（标点与汉字分离）")
    if d.get("centerBad"):
        problems.append(f"{d['centerBad']} 个拼音未与汉字居中对齐")
    if d.get("rtCount", 0) > 0 and d.get("tones", 0) == 0 and not d.get("noToneMode"):
        problems.append("未检测到声调符号")
    return problems


def main(files: list[str]) -> int:
    exe = find_browser()
    if not exe:
        print(json.dumps({"ok": True, "skipped": "no browser found"}, ensure_ascii=False))
        return 0
    all_ok = True
    for f in files:
        p = Path(f)
        if not p.is_file():
            print(json.dumps({"file": f, "ok": False, "problems": ["文件不存在"]},
                             ensure_ascii=False))
            all_ok = False
            continue
        for width in (1000, 500, 375):
            d = run_check(exe, p, width)
            probs = verdict(d)
            line = {"file": p.name, "viewport": d.get("viewport", f"{width}px"),
                    "ok": not probs, "problems": probs}
            if probs:
                all_ok = False
            print(json.dumps(line, ensure_ascii=False))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
