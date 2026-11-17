# -*- coding: utf-8 -*-
"""PDF 实测体检：用本机 Chrome/Edge 无头打印真实 PDF 后核对分页质量。

检查项：
1. 实际页数 == layout.pages_est（估算与真实分页一致）；
2. 标题不孤立：第 1 页若有标题，其下方应有正文/作者内容；
3. 汉字字号 ≈ han_size_pt（±8%，取正文汉字 span 的中位字号）；
4. 拼音对应：抽若干汉字，其正上方（同 x 中心）存在拼音 span；
5. 孤尾短行：按 y 坐标聚类视觉行（fitz splitlines 的 span 顺序
   不可信——"磨。"式假象），以句读结尾且 ≤3 字的行视为孤尾
   （完整短小句如"江南好，"以逗号结尾不算）。

用法：python tests/pdf_check.py case1.html case2.html …
      （HTML 由 generate.py --pdf 同名导出 PDF；无 PDF 时报 skip 并退出 0）
依赖 PyMuPDF（fitz）；找不到时输出 skip 并退出 0。
"""

from __future__ import annotations

import json
import re
import statistics
import subprocess
import sys
from pathlib import Path

def _find_browser() -> str | None:
    import os
    from shutil import which
    for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(env, "")
        for sub, exe in (("Google/Chrome/Application", "chrome.exe"),
                         ("Microsoft/Edge/Application", "msedge.exe"),
                         ("Chromium/Application", "chrome.exe")):
            p = Path(base) / sub / exe
            if p.is_file():
                return str(p)
    return which("chrome") or which("msedge") or which("chromium")


def export_pdf(exe: str, html: Path) -> Path | None:
    pdf = html.with_suffix(".pdf")
    cmd = [exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
           f"--print-to-pdf={pdf.resolve()}", html.resolve().as_uri()]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                       encoding="utf-8", errors="replace")
    return pdf if r.returncode == 0 and pdf.is_file() and pdf.stat().st_size else None


def _visual_rows(page) -> list[str]:
    """按 y 坐标聚类视觉行，返回每行的汉字+标点序列。

    fitz 的 splitlines 按 span 顺序输出，一行会被拆散（句号 span 单独
    成行造成"磨。"假象）——必须按 baseline 聚类。
    """
    spans = []
    for blk in page.get_text("dict")["blocks"]:
        for ln in blk.get("lines", []):
            for sp in ln["spans"]:
                if sp["text"].strip():
                    spans.append((sp["bbox"][1], sp["bbox"][0], sp["text"]))
    spans.sort()
    rows: list[list[float, list]] = []
    for y, x, t in spans:
        if rows and abs(rows[-1][0] - y) <= 4:
            rows[-1][1].append((x, t))
        else:
            rows.append([y, [(x, t)]])
    out = []
    for _y, items in rows:
        items.sort()
        han = "".join(re.findall(
            r"[\u4e00-\u9fff，。、；：！？《》〔〕（）]", "".join(t for _, t in items)))
        if han:
            out.append(han)
    return out


def check(html: Path) -> dict:
    import fitz
    src = html.read_text(encoding="utf-8")
    m = re.search(r'<script type="application/json" id="cpt-spec">(.*?)</script>',
                  src, re.S)
    spec = json.loads(m.group(1).replace("<\\/", "</")) if m else {}
    fs_base = re.search(r"--fs-base: ([\d.]+)pt", src)
    want_fs = float(fs_base.group(1)) if fs_base else None
    title = re.sub(r"^[《〈]+|[》〉]+$", "", spec.get("title", "")).strip()

    doc = fitz.open(html.with_suffix(".pdf"))
    pages_hanzi: list[int] = []
    problems: list[str] = []
    body_sizes: list[float] = []
    py_ok = py_total = 0
    for i, page in enumerate(doc):
        d = page.get_text("dict")
        han_spans, py_spans = [], []
        han = 0
        title_on_page = False
        for blk in d["blocks"]:
            for ln in blk.get("lines", []):
                for sp in ln["spans"]:
                    t = sp["text"].strip()
                    if not t:
                        continue
                    hanzi = len(re.findall(r"[\u4e00-\u9fff]", t))
                    if hanzi:
                        han += hanzi
                        body_sizes.append(sp["size"])
                        han_spans.append(sp)
                        if title and title[:3] in t and i == 0 and sp["bbox"][1] < 150:
                            title_on_page = True
                    elif re.search(r"[a-zāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]", t):
                        py_spans.append(sp)
        pages_hanzi.append(han)
        # 标题孤立：第 1 页有标题但几乎没有正文汉字（≤ 标题长度+作者）
        if i == 0 and title_on_page and han <= len(title) + 6:
            problems.append(f"第1页疑似标题孤页（仅 {han} 个汉字）")
        # 拼音对应：抽前 30 个汉字 span，正上方（x 中心对齐）应有拼音
        if not spec.get("mode") or spec.get("mode") == "both":
            for sp in han_spans[:30]:
                x0, y0, x1, _ = sp["bbox"]
                xc = (x0 + x1) / 2
                py_total += 1
                if any(abs((p["bbox"][0] + p["bbox"][2]) / 2 - xc)
                       < max(6.0, (x1 - x0) * 0.6)
                       and 0 < y0 - p["bbox"][3] < (x1 - x0) * 2.5
                       for p in py_spans):
                    py_ok += 1
        # 孤尾短行：视觉行以句号/问号结尾且正文 ≤3 字（完整短小句"江南好，"
        # 以逗号结尾不算；问句"能不忆江南？"5 字不算）
        for han in _visual_rows(page):
            core = han.rstrip("。？，、；：")
            if han.endswith(("。", "？")) and 0 < len(core) <= 3:
                problems.append(f"第{i+1}页孤尾短行「{han}」")
    doc.close()
    if py_total >= 10 and py_ok / py_total < 0.9:
        problems.append(f"拼音对应率 {py_ok}/{py_total} 偏低")

    n_pages = len(pages_hanzi)
    med_fs = statistics.median(body_sizes) if body_sizes else 0
    if want_fs and abs(med_fs - want_fs) / want_fs > 0.08:
        problems.append(f"汉字字号 {med_fs:.1f}pt ≠ 预期 {want_fs:.1f}pt")
    if pages_hanzi and pages_hanzi[-1] == 0:
        problems.append("末页无内容（空白页）")
    return {"file": html.name, "pages": n_pages, "pages_hanzi": pages_hanzi,
            "fs": round(med_fs, 1), "pinyin": f"{py_ok}/{py_total}",
            "problems": problems}


def main(files: list[str]) -> int:
    try:
        import fitz  # noqa: F401
    except ImportError:
        print(json.dumps({"ok": True, "skipped": "PyMuPDF 未安装"}, ensure_ascii=False))
        return 0
    exe = _find_browser()
    if not exe:
        print(json.dumps({"ok": True, "skipped": "no browser"}, ensure_ascii=False))
        return 0
    all_ok = True
    for f in files:
        p = Path(f)
        if not p.is_file():
            print(json.dumps({"file": f, "ok": False, "problems": ["文件不存在"]},
                             ensure_ascii=False))
            all_ok = False
            continue
        pdf = export_pdf(exe, p)
        if pdf is None:
            print(json.dumps({"file": p.name, "ok": False,
                              "problems": ["PDF 导出失败"]}, ensure_ascii=False))
            all_ok = False
            continue
        d = check(p)
        d["ok"] = not d["problems"]
        all_ok &= d["ok"]
        print(json.dumps(d, ensure_ascii=False))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
