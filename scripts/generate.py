# -*- coding: utf-8 -*-
"""chinese-pinyin-typesetting 生成入口（标准 Python CLI，无 Agent 运行时依赖）。

用法：

  python scripts/generate.py --spec spec.json [--out 输出.html] [--pdf]
  python scripts/generate.py --from-html 上次.html [--set mode=hanzi]
                                [--override '{"line":3,"char":2,"tone":4}']
                                [--out 新.html] [--pdf]
  python scripts/generate.py --text-file poem.txt / --text "..."

spec.json 结构与示例见 SKILL.md / references/spec.md。
stdout 输出 JSON 摘要（含 review 多音字提示）；退出码 0=成功 2=输入错误。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import pronunciation as pr  # noqa: E402
import renderer as rd  # noqa: E402


# ---------------------------------------------------------------------------
# spec 装载与修补
# ---------------------------------------------------------------------------

AUTO_TEMPLATE = ("auto", "")


def guess_template(text: str) -> str:
    """默认模板选择：诗行（行短、多行、居中）→ poem；否则 reading。"""
    probe = pr.annotate(text)
    return "poem" if rd._is_verse_like(probe) else "reading"


def parse_text_file(raw: str) -> dict:
    """从纯文本自动解析 title/author/dynasty/body。"""
    lines = [ln.strip() for ln in raw.strip().splitlines()]
    lines = [ln for ln in lines if ln]
    spec: dict = {"text": ""}
    idx = 0
    if lines and idx < len(lines):
        first = lines[0]
        m = re.match(r"^[《〈](.+?)[》〉]$", first)
        if m:
            spec["title"] = m.group(1)
            idx = 1
        elif len(lines) >= 3 and len(first) <= 12 and not re.search(r"[，。！？；：]", first):
            spec["title"] = first
            idx = 1
    if idx < len(lines):
        second = lines[idx]
        am = re.match(
            r"^(?:〔|\[|（|\()?\s*([唐宋元明清汉魏晋南北朝隋]{1,2})\s*(?:〕|\]|）|\))?\s*[·。/／]?\s*(\S{1,8})$",
            second)
        if am:
            spec["dynasty"] = am.group(1)
            spec["author"] = am.group(2)
            idx += 1
        elif (len(second) <= 6 and len(lines) - idx >= 3
              and not re.search(r"[，。！？；：、—…《》]", second)):
            spec["author"] = second   # 无朝代的短作者行（如"李白"）
            idx += 1
    spec["text"] = "\n".join(lines[idx:])
    return spec


def load_spec(args) -> dict:
    if args.spec:
        p = Path(args.spec)
        if not p.is_file():
            raise pr.PinyinSpecError(f"找不到 spec 文件：{args.spec}")
        try:
            spec = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise pr.PinyinSpecError(f"spec.json 解析失败：{e}")
    elif args.from_html:
        p = Path(args.from_html)
        if not p.is_file():
            raise pr.PinyinSpecError(f"找不到 HTML 文件：{args.from_html}")
        spec = rd.extract_spec_from_html(p)
    elif args.text_file:
        p = Path(args.text_file)
        if not p.is_file():
            raise pr.PinyinSpecError(f"找不到文本文件：{args.text_file}")
        spec = parse_text_file(p.read_text(encoding="utf-8-sig"))
    elif args.text is not None:
        spec = parse_text_file(args.text)
        if args.title:
            spec["title"] = args.title
    else:
        raise pr.PinyinSpecError(
            "需要 --spec / --from-html / --text-file / --text 之一提供内容")
    for k in ("title", "author", "dynasty"):
        if args and getattr(args, k, None):
            spec[k] = getattr(args, k)
    if getattr(args, "template", None):
        spec["template"] = args.template
    return spec


def _parse_value(v: str):
    try:
        return json.loads(v)
    except (json.JSONDecodeError, ValueError):
        return v


def apply_sets(spec: dict, sets: list[str]) -> None:
    for s in sets or []:
        if "=" not in s:
            raise pr.PinyinSpecError(f"--set 需要 key=value 形式：{s}")
        k, v = s.split("=", 1)
        k = k.strip()
        if not k:
            raise pr.PinyinSpecError(f"--set 键为空：{s}")
        spec[k] = _parse_value(v)


def apply_override_args(spec: dict, overrides: list[str]) -> None:
    for o in overrides or []:
        try:
            obj = json.loads(o)
        except json.JSONDecodeError as e:
            raise pr.PinyinSpecError(f"--override JSON 解析失败：{o}（{e}）")
        if not isinstance(obj, dict):
            raise pr.PinyinSpecError(f"--override 需要对象：{o}")
        spec.setdefault("overrides", []).append(obj)


# ---------------------------------------------------------------------------
# 输出文件名
# ---------------------------------------------------------------------------

_MODE_SUFFIX = {
    "both": "注音版",
    "hanzi": "背诵版",
    "pinyin": "看拼音写汉字",
    "blank_pinyin": "注音练习",
}


def default_output_name(spec: dict, template: str) -> str:
    base = (spec.get("title") or "注音文档").strip()[:30] or "注音文档"
    base = re.sub(r'[\\/:*?"<>|《》〔〕]', "", base).strip() or "注音文档"
    mode = spec.get("mode") or "both"
    suffix = _MODE_SUFFIX.get(mode, "注音版")
    if template == "worksheet":
        name = f"{base}（默写·{suffix}）.html"
    elif template == "reading":
        name = f"{base}（{suffix}）.html"
    else:
        name = f"{base}（{suffix}）.html"
    return name


# ---------------------------------------------------------------------------
# PDF（可选；本机有 Chrome/Edge 时可用，其余环境如实报告不可用）
# ---------------------------------------------------------------------------

def _find_browser() -> str | None:
    cands = []
    for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = Path(__import__("os").environ.get(env, ""))
        if base:
            cands += [
                base / "Google/Chrome/Application/chrome.exe",
                base / "Microsoft/Edge/Application/msedge.exe",
                base / "Chromium/Application/chrome.exe",
            ]
    for c in cands:
        if c.is_file():
            return str(c)
    return shutil.which("chrome") or shutil.which("msedge") \
        or shutil.which("chromium") or shutil.which("google-chrome")


def export_pdf(html_path: Path) -> dict:
    exe = _find_browser()
    if not exe:
        return {"ok": False, "reason": "未找到本机 Chrome/Edge，无法导出 PDF（可在浏览器中打开 HTML 后 Ctrl+P 打印为 PDF）"}
    pdf_path = html_path.resolve().with_suffix(".pdf")   # Chrome 需绝对路径
    cmd = [exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
           f"--print-to-pdf={pdf_path}", html_path.resolve().as_uri()]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90,
                           encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "浏览器打印超时"}
    except OSError as e:
        return {"ok": False, "reason": f"浏览器启动失败：{e}"}
    if r.returncode != 0 or not pdf_path.is_file() or pdf_path.stat().st_size == 0:
        return {"ok": False, "reason": f"浏览器返回码 {r.returncode}：{(r.stderr or '')[:200]}"}
    return {"ok": True, "output": str(html_path.with_suffix(".pdf"))}


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def build(args) -> dict:
    spec = load_spec(args)
    apply_sets(spec, args.set or [])
    apply_override_args(spec, args.override or [])

    text = spec.get("text")
    if not isinstance(text, str) or not text.strip():
        raise pr.PinyinSpecError("spec 缺少 text（正文）字段")

    template = str(spec.get("template") or "auto").lower()
    if template == "auto":
        template = guess_template(text)
    if template not in rd.TEMPLATES + ("auto",):
        raise pr.PinyinSpecError(f"未知模板 {template}（可选 auto/poem/reading/worksheet）")
    spec["_template"] = template

    ann = pr.annotate(text, overrides=spec.get("overrides"),
                      sandhi=spec.get("tone_sandhi", "yi_bu"))
    ann_title = None
    if spec.get("title") and spec.get("annotate_title", True):
        t = str(spec["title"])
        if any(pr.is_han_char(c) for c in t):
            ann_title = pr.annotate(re.sub(r"^[《〈]+|[》〉]+$", "", t))
    ann_author = None
    if spec.get("author") and spec.get("annotate_author", False):
        d = str(spec.get("dynasty") or "").strip()
        # 注音对象含朝代：〔唐〕与作者名同一行注音单元（共享 rowh 基线），
        # 否则 annotate_author 时朝代会被整个丢掉
        label = f"〔{d}〕{spec['author']}" if d else str(spec["author"])
        ann_author = pr.annotate(label)

    out = Path(args.out) if args.out else Path(default_output_name(spec, template))
    if out.parent and not out.parent.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
    info = rd.render_document(spec, ann, ann_title, ann_author, out)

    warnings = []
    if ann.missing:
        warnings.append(f"{len(ann.missing)} 个汉字无拼音（生僻字）：" +
                        "".join(m["char"] for m in ann.missing[:20]))
    if info.get("clause_wrap"):
        warnings.append("个别诗句过长，已在句读处折行")
    layout = info.get("layout") or {}
    if layout.get("strategy") == "couplet":
        warnings.append("已按一联一行合并排版（couplet），可用 --set couplet=false 改回一句一行")
    for ov in (layout.get("overflow") or [])[:3]:
        warnings.append(
            f"第 {ov['stanza']} 节「{ov['text']}…」超出栏宽，已在句读/标点处折行；"
            "可减小 han_size、改单栏（columns=1）或降低页数目标")
    if layout.get("target_pages") and layout.get("target_met") is False:
        warnings.append(f"无法达到 {layout['target_pages']} 页目标（当前约 "
                        f"{layout['pages_est']} 页）：字号已到 readability 下限，"
                        f"可改小 han_size 下限来源或接受多页")
    if layout.get("strategy") == "flow" and layout.get("target_pages"):
        warnings.append("target_pages 当前仅作用于诗行排版（poem/诗行 worksheet），阅读流未启用")

    result = {
        "ok": True,
        "output": str(out),
        "template": template,
        "mode": info["mode"],
        "columns": info["columns"],
        "hanzi_count": ann.hanzi_count,
        "han_size_pt": info["han_size"],
        "pinyin_size_pt": info["pinyin_size"],
        "layout": layout,
        "overrides_applied": ann.applied_overrides,
        "review": ann.review,
        "notes": ann.notes,
        "warnings": warnings,
        "spec_echo": spec,
    }
    if args.pdf:
        result["pdf"] = export_pdf(out)
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="中文拼音注音排版生成器")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--spec", help="spec JSON 文件路径")
    src.add_argument("--from-html", help="从本 Skill 生成的 HTML 恢复 spec 重新生成")
    src.add_argument("--text-file", help="纯文本文件（自动识别标题/作者）")
    src.add_argument("--text", help="直接给正文文本（短内容）")
    ap.add_argument("--title", help="覆盖标题")
    ap.add_argument("--author", help="覆盖作者")
    ap.add_argument("--template", choices=["auto", "poem", "reading", "worksheet"])
    ap.add_argument("--set", action="append", metavar="KEY=VALUE",
                    help="修改 spec 字段，如 --set mode=hanzi --set han_size=36")
    ap.add_argument("--override", action="append", metavar="JSON",
                    help="追加读音覆盖，如 --override '{\"line\":3,\"char\":2,\"tone\":4}'")
    ap.add_argument("--out", help="输出 HTML 路径（默认按标题命名）")
    ap.add_argument("--pdf", action="store_true",
                    help="尝试用本机 Chrome/Edge 导出 PDF（不可用时如实报告）")
    args = ap.parse_args(argv)

    try:
        result = build(args)
    except (pr.PinyinSpecError, rd.RenderError) as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
