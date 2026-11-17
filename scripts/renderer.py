# -*- coding: utf-8 -*-
"""注音排版渲染器：Annotation → 自包含 HTML。

三种模板（templates/）：poem 古诗背诵版 / reading 课文阅读版 / worksheet 默写练习版。
共用同一份注音数据与同一套注音单元 CSS（base.css），注音单元用
inline-flex 列布局显式控制拼音行高与汉字行高，不依赖浏览器默认 ruby 排版。

四种显示模式（mode）对三种模板通用：
  both         拼音 + 汉字
  hanzi        只显汉字（背诵/朗诵）
  pinyin       只显拼音，汉字位为田字格（看拼音写汉字）
  blank_pinyin 汉字 + 拼音书写空线（给汉字标拼音练习）
"""

from __future__ import annotations

import html as _html
import json
import math
import re
from pathlib import Path

from pronunciation import Annotation, Token

_HERE = Path(__file__).resolve().parent
_TPL_DIR = _HERE.parent / "templates"

TEMPLATES = ("poem", "reading", "worksheet")
MODES = ("both", "hanzi", "pinyin", "blank_pinyin")

PAGE_SIZES = {  # mm, 竖版 (w, h)
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
    "LETTER": (215.9, 279.4),
}

FONT_STACKS = {
    "kai": '"KaiTi", "楷体", "STKaiti", "Kaiti SC", "Kaiti TC", "DFKai-SB", '
           '"AR PL UKai CN", "Noto Serif CJK SC", "Noto Sans CJK SC", serif',
    "song": '"SimSun", "宋体", "Songti SC", "STSong", "NSimSun", '
            '"Noto Serif CJK SC", serif',
    "hei": '"Microsoft YaHei", "微软雅黑", "PingFang SC", "Hiragino Sans GB", '
           '"Source Han Sans SC", "Noto Sans CJK SC", sans-serif',
}

# 开启类标点（行尾禁排）：排版时并入后一个内容单元；
# 其余标点一律视为闭合类（行首禁排），并入前一个内容单元。
_OPENING_PUNCT = set("（〔【｛《〈「『“‘([{<«")

# 双栏栏间距 = 汉字字号 × 该系数（与 base.css 中 column-gap: calc(var(--fs) * 2.5) 保持同步）
COLUMN_GAP_K = 2.5


class RenderError(ValueError):
    pass


# ---------------------------------------------------------------------------
# 配置解析与默认值
# ---------------------------------------------------------------------------

def _defaults(template: str) -> dict:
    return {
        "poem":      {"han_size": 32, "vgap": 1.0},
        "reading":   {"han_size": 15.5, "vgap": 1.0, "lgap": 0.7},
        "worksheet": {"han_size": 24, "vgap": 0.9, "lgap": 0.7},
    }.get(template, {"han_size": 24, "vgap": 1.0, "lgap": 0.7})


def resolve_config(spec: dict, template: str) -> dict:
    d = _defaults(template)
    cfg = {
        "template": template,
        "han_size": float(spec.get("han_size") or d["han_size"]),
        "pinyin_ratio": float(spec.get("pinyin_ratio") or 0.55),
        "vgap": float(spec.get("line_gap_scale") or d.get("vgap", 1.0)),
        "lgap": float(spec.get("line_gap_scale") or d.get("lgap", 0.7)),
        "page": str(spec.get("page") or "A4").upper(),
        "landscape": bool(spec.get("landscape")),
        "columns": spec.get("columns", 1),
        "margin_mm": spec.get("margin_mm", 18.0),
        "font": str(spec.get("font") or "kai").lower(),
        "mode": str(spec.get("mode") or "both").lower(),
        "annotate_title": bool(spec.get("annotate_title", True)),
        "annotate_author": bool(spec.get("annotate_author", False)),
        "copy_rows": int(spec.get("copy_rows") or (1 if template == "worksheet" else 0)),
        "footer": spec.get("footer") or "",
    }
    if cfg["page"] not in PAGE_SIZES:
        raise RenderError(f"不支持的纸张 {cfg['page']}（可选 A4/A5/Letter）")
    try:
        cfg["columns"] = int(cfg["columns"])
    except (TypeError, ValueError):
        raise RenderError(f"columns 需为 1 或 2（当前 {cfg['columns']!r}）")
    if cfg["columns"] not in (1, 2):
        raise RenderError(f"columns 需为 1 或 2（当前 {cfg['columns']}）")
    if cfg["font"] not in FONT_STACKS:
        raise RenderError(f"不支持的字体 {cfg['font']}（可选 kai/song/hei）")
    if cfg["mode"] not in MODES:
        raise RenderError(f"不支持的 mode {cfg['mode']}（可选 {'/'.join(MODES)}）")
    if not (8.0 <= cfg["han_size"] <= 120.0):
        raise RenderError("han_size 需在 8-120 pt 之间")
    if not (0.25 <= cfg["pinyin_ratio"] <= 0.8):
        raise RenderError("pinyin_ratio 需在 0.25-0.8 之间")
    if isinstance(cfg["margin_mm"], (int, float)):
        margin = float(cfg["margin_mm"])
        cfg["margin_mm"] = (margin, margin)
    mv, mh = cfg["margin_mm"]
    if not (6.0 <= mv <= 40.0 and 6.0 <= mh <= 40.0):
        raise RenderError("margin_mm 需在 6-40 mm 之间")
    if not (0 <= cfg["copy_rows"] <= 3):
        raise RenderError("copy_rows 需在 0-3 之间")
    if spec.get("pinyin_size"):
        cfg["pinyin_ratio"] = float(spec["pinyin_size"]) / cfg["han_size"]
    return cfg


# ---------------------------------------------------------------------------
# 注音单元 HTML
# ---------------------------------------------------------------------------

def _han_cell(t: Token, mode: str) -> str:
    if mode == "pinyin":                      # 看拼音写汉字：汉字位为田字格
        return (f'<ruby class="c"><span class="tz" aria-label="{_html.escape(t.text)}">'
                f'</span><rt class="y">{_html.escape(t.pinyin or "")}</rt></ruby>')
    body = f'<span class="h">{_html.escape(t.text)}</span>'
    if mode == "hanzi":                       # 只显汉字
        return f'<ruby class="c">{body}</ruby>'
    if mode == "blank_pinyin":                # 给汉字标拼音
        rt = '<rt class="y blank">&nbsp;</rt>'
    else:
        rt = f'<rt class="y">{_html.escape(t.pinyin or "")}</rt>'
    return f'<ruby class="c">{body}{rt}</ruby>'


_TUCK_PUNCT = set("，。、")   # 墨迹在左半且无右伸笔画：裁掉空白右半收窄占位


def _punct_cell(t: Token, mode: str) -> str:
    p = _html.escape(t.text)
    rt = "" if mode == "hanzi" else f'<rt class="y">&nbsp;</rt>'
    cls = "c p tuck" if t.text in _TUCK_PUNCT else "c p"
    return f'<ruby class="{cls}"><span class="h">{p}</span>{rt}</ruby>'


def _latin_cell(t: Token, mode: str) -> str:
    w = _html.escape(t.text)
    rt = "" if mode == "hanzi" else f'<rt class="y">&nbsp;</rt>'
    return f'<ruby class="c lat"><span class="h">{w}</span>{rt}</ruby>'


def _space_cell(t: Token) -> str:
    return f'<ruby class="c sp"><span class="h">&#8201;</span></ruby>'


def line_cells(tokens, mode: str, *, poem: bool, allow_break: bool) -> str:
    """一行/一段的注音 HTML。

    poem=True：诗句排版，句内不断行；allow_break=True 时仅在句读后允许折行。
    poem=False：流式正文按"簇"输出（_flow_clusters）——闭合类标点并入前一个
    内容单元、开启类标点并入后一个内容单元，簇间 <wbr>、簇内零断点，
    从结构上保证避头尾（标点不落行首、左标点不落行尾）。
    """
    if poem:
        parts: list[str] = []
        for tok in tokens:
            if tok.kind == "han":
                parts.append(_han_cell(tok, mode))
                if allow_break:
                    parts.append("<wbr>")
            elif tok.kind == "punct":
                parts.append(_punct_cell(tok, mode))
                parts.append("<wbr>")     # 断行只可能出现在句读之后
            elif tok.kind == "latin":
                parts.append(_latin_cell(tok, mode))
            else:
                parts.append(_space_cell(tok))
        return "".join(parts)
    return _flow_clusters(tokens, mode)


def _flow_clusters(tokens, mode: str) -> str:
    """流式正文聚类输出。

    一个簇 = [开启标点… + 内容单元(汉字/拉丁词) + 其后闭合标点…]，
    连续闭合标点（如 。」）并入同一簇。簇间输出 <wbr>（空白处输出空格），
    多单元簇外包 .nb（white-space:nowrap），簇内无任何断点。
    """
    clusters: list[tuple[str, list[str]]] = []   # (前导空白, 单元列表)
    pending_open: list[str] = []
    sep = ""
    for tok in tokens:
        if tok.kind in ("han", "latin"):
            cell = _han_cell(tok, mode) if tok.kind == "han" else _latin_cell(tok, mode)
            clusters.append((sep, pending_open + [cell]))
            pending_open, sep = [], ""
        elif tok.kind == "punct":
            cell = _punct_cell(tok, mode)
            if tok.text in _OPENING_PUNCT:
                pending_open.append(cell)          # 行尾禁排 → 绑定后续内容
            elif clusters:
                clusters[-1][1].append(cell)      # 行首禁排 → 并入前簇
            else:
                clusters.append((sep, pending_open + [cell]))
                pending_open, sep = [], ""
        else:                                      # 空白：簇间分隔符
            if pending_open:
                pending_open.append(" ")
            else:
                sep = " "
    if pending_open:                                # 段末孤立开启标点：自成簇
        clusters.append((sep, pending_open))
    parts: list[str] = []
    for i, (s, cells) in enumerate(clusters):
        if i:
            parts.append(s or "<wbr>")
        elif s:
            parts.append(s)
        joined = "".join(cells)
        parts.append(f'<span class="nb">{joined}</span>' if len(cells) > 1 else joined)
    return "".join(parts)


# ---------------------------------------------------------------------------
# 版面计算
# ---------------------------------------------------------------------------

def _max_pinyin_len(ann: Annotation) -> int:
    n = 1
    for t in ann.han_tokens():
        if t.pinyin:
            n = max(n, len(t.pinyin))
    return min(n, 8)


def _line_units(toks: list[Token], cell_r: float) -> float:
    u = 0.0
    for t in toks:
        if t.kind == "han":
            u += cell_r
        elif t.kind == "punct":
            u += 0.56 if t.text in _TUCK_PUNCT else 1.02
        elif t.kind == "latin":
            u += len(t.text) * 0.55
        else:
            u += 0.5
    return u


def _verse_fragments(ann: Annotation) -> tuple[list[list[Token]], int]:
    """返回 (所有诗句片段, 节数量)。一句一行排版的基本单位。"""
    frags: list[list[Token]] = []
    n_stanza = 0
    for stanza in _stanzas(ann):
        n_stanza += 1
        for toks in stanza:
            frags.extend(_split_verse(toks))
    return frags, max(n_stanza, 1)


def _pack_columns(n_rows_per_stanza: list[int], cols: int) -> list[list[int]]:
    """把各节的行数贪心装栏（节不跨栏，与 CSS break-inside:avoid 一致）。

    返回每栏 [行数, 节数]；cols=1 时等价于全部装一栏。
    """
    stat = [[0, 0] for _ in range(cols)]
    for n in sorted(n_rows_per_stanza, reverse=True):
        i = min(range(cols), key=lambda k: stat[k][0])
        stat[i][0] += n
        stat[i][1] += 1
    return stat


def _fit_han_size(cfg: dict, ann: Annotation) -> tuple[float, float, float, bool]:
    """横向（最长句不超页宽）+ 纵向（总高不超页高）联合适配。

    所有高度都是 fs 的线性函数，可直接解出 fs 上限。
    返回 (最终汉字字号 pt, cell_r, 最长句 units, 是否放行句中折行)。
    """
    pw, ph = PAGE_SIZES[cfg["page"]]
    if cfg["landscape"]:
        pw, ph = PAGE_SIZES[cfg["page"]][::-1]
    mv, mh = cfg["margin_mm"]
    content_w = (pw - 2 * mh) / 25.4 * 72.0
    content_h = (ph - 2 * mv) / 25.4 * 72.0

    py_len = _max_pinyin_len(ann)
    cell_r = max(1.22, py_len * cfg["pinyin_ratio"] * 0.52 + 0.14)
    if cfg["mode"] == "hanzi":
        cell_r = 1.12

    frags, _ = _verse_fragments(ann)
    max_units = max((_line_units(f, cell_r) for f in frags), default=cell_r)
    # 双栏：最长句须放进半栏宽，栏间距随字号缩放 → 一次解出字号上限
    cols = cfg["columns"]
    fs_w = content_w / (cols * max_units + COLUMN_GAP_K * (cols - 1))

    row_k = cfg["pinyin_ratio"] * 1.7 + 1.18          # rowh / fs
    header_k = 0.0
    if cfg.get("_has_title"):
        header_k += 1.32 * row_k + 1.35
        if cfg.get("_has_author"):
            header_k += 0.72 + 0.5
    if cfg["template"] == "worksheet":
        header_k += 0.62 + 0.8                        # 姓名/日期栏
    tian_k = 2.0 * cfg["copy_rows"] if cfg["copy_rows"] else 0.0
    # 纵向：按节贪心分栏（节不跨栏），取最高一栏的高度
    rows_per_stanza = [
        sum(len(_split_verse(toks)) for toks in stanza) for stanza in _stanzas(ann)
    ] or [len(frags)]
    body_k = max(
        rows * (row_k + cfg["vgap"]) - cfg["vgap"] + max(st - 1, 0) * 1.6 + rows * tian_k
        for rows, st in _pack_columns(rows_per_stanza, cols)
    )
    fs_h = content_h / max(header_k + body_k, 1.0)

    fs = min(cfg["han_size"], fs_w, fs_h)
    wrap = False
    floor = max(cfg["han_size"] * 0.55, 10.0)
    if fs < floor:
        fs = floor
        if fs_w < floor:
            wrap = True
    return fs, cell_r, max_units, wrap


# ---------------------------------------------------------------------------
# 页眉 / 主体 / 模板填充
# ---------------------------------------------------------------------------

def _title_html(title: str, ann_t: Annotation | None, cfg: dict,
                fs: float, content_pt: float) -> tuple[str, float]:
    """返回 (标题 HTML, 标题字号缩放系数)。"""
    title_show = re.sub(r"^[《〈]+|[》〉]+$", "", title.strip())
    if not title_show:
        return "", 1.32
    t_scale = 1.32
    if ann_t is not None:
        py_len = _max_pinyin_len(ann_t)
        t_cell_r = max(1.22, py_len * cfg["pinyin_ratio"] * 0.52 + 0.14)
        units = _line_units(ann_t.lines[0] if ann_t.lines else [], t_cell_r)
        t_scale = min(t_scale, (content_pt / max(units, 1)) / fs)
        inner = line_cells(ann_t.lines[0], cfg["mode"], poem=True, allow_break=False) \
            if ann_t.lines else _html.escape(title_show)
    else:
        inner = _html.escape(title_show)
    return f'<div class="t-line">{inner}</div>', max(t_scale, 0.9)


def _author_html(author: str, dynasty: str | None, ann_a: Annotation | None,
                 cfg: dict) -> str:
    a = (author or "").strip()
    d = (dynasty or "").strip()
    if not a and not d:
        return ""
    label = f"〔{d}〕{a}" if d else a
    if ann_a is not None and ann_a.lines:
        inner = line_cells(ann_a.lines[0], cfg["mode"], poem=True, allow_break=False)
    else:
        inner = _html.escape(label)
    return f'<div class="a-line">{inner}</div>'


def build_header(title, ann_t, author, dynasty, ann_a, cfg, fs, content_pt):
    parts = []
    t_scale = 1.32
    if title:
        t_html, t_scale = _title_html(title, ann_t, cfg, fs, content_pt)
        parts.append(t_html)
        au = _author_html(author, dynasty, ann_a, cfg)
        if au:
            parts.append(au)
    return (f'<header class="hd">{"".join(parts)}</header>' if parts else ""), t_scale


def _stanzas(ann: Annotation):
    """按空行分节：返回 [ [line tokens...], ... ]。"""
    stanzas, cur = [], []
    for toks in ann.lines:
        if toks:
            cur.append(toks)
        elif cur:
            stanzas.append(cur)
            cur = []
    if cur:
        stanzas.append(cur)
    return stanzas or [[t] for t in ann.lines if t]


def _tian_row(n: int, wrap: bool) -> str:
    if n <= 0:
        return ""
    boxes = "<wbr>".join('<span class="tz"></span>' for _ in range(n))
    cls = " tian-wrap" if wrap else ""
    return f'<div class="tian-row{cls}">{boxes}</div>'


def _split_verse(toks: list[Token]) -> list[list[Token]]:
    """诗行排版：在句读（，。、；：！？）处把源行拆成"一句一行"，
    标点保留在句末。非句读符号（《》""等）不拆。"""
    clause_end = _TUCK_PUNCT | set("！？；：")
    frags: list[list[Token]] = []
    cur: list[Token] = []
    for t in toks:
        cur.append(t)
        if t.kind == "punct" and t.text in clause_end:
            frags.append(cur)
            cur = []
    if cur:
        frags.append(cur)
    return [f for f in frags if any(x.is_han for x in f)] or [toks]


def build_poem_body(ann: Annotation, cfg: dict, *, fs: float,
                    tian: bool = False, wrap: bool = False) -> str:
    out = []
    for stanza in _stanzas(ann):
        lines_html = []
        for toks in stanza:
            for frag in _split_verse(toks):
                v = line_cells(frag, cfg["mode"], poem=True, allow_break=wrap)
                lines_html.append(f'<div class="v">{v}</div>')
                if tian:
                    n = sum(1 for t in frag if t.is_han)
                    lines_html.append(_tian_row(n, wrap=n > 18))
        out.append(f'<div class="stanza">{"".join(lines_html)}</div>')
    return "".join(out)


def build_reading_body(ann: Annotation, cfg: dict) -> str:
    out = []
    for stanza in _stanzas(ann):
        for toks in stanza:
            p = line_cells(toks, cfg["mode"], poem=False, allow_break=True)
            out.append(f'<p class="para">{p}</p>')
    return "".join(out)


def _page_css(cfg: dict) -> str:
    pw, ph = PAGE_SIZES[cfg["page"]]
    if cfg["landscape"]:
        pw, ph = ph, pw
    orient = "landscape" if cfg["landscape"] else "portrait"
    mv, mh = cfg["margin_mm"]
    return (f"@page {{ size: {cfg['page']} {orient}; margin: {mv}mm {mh}mm; }}")


def _css_vars(cfg: dict, fs: float, cell_r: float, units: float,
              t_scale: float) -> str:
    pw = PAGE_SIZES[cfg["page"]][0]
    if cfg["landscape"]:
        pw = PAGE_SIZES[cfg["page"]][1]
    mv, mh = cfg["margin_mm"]
    # 派生变量挂在 .sheet 上：移动端媒体查询缩放 --fs 时全部级联重算
    return f"""
.sheet {{
  --fs-base: {fs:.2f}pt; --fs: {fs:.2f}pt;
  --pyr: {cfg['pinyin_ratio']:.4f}; --cellr: {cell_r:.4f};
  --units: {max(units, 1):.2f}; --t-scale: {t_scale:.4f};
  --py: calc(var(--fs) * var(--pyr));
  --cell: calc(var(--fs) * var(--cellr));
  --hzlh: calc(var(--fs) * 1.18);
  --pyh: calc(var(--py) * 1.7);
  --rowh: calc(var(--pyh) + var(--hzlh));
  --fst: calc(var(--fs) * var(--t-scale));
  --t-cell: calc(var(--fst) * var(--cellr));
  --t-hzlh: calc(var(--fst) * 1.18);
  --t-py: calc(var(--fst) * var(--pyr));
  --t-pyh: calc(var(--t-py) * 1.7);
  --t-rowh: calc(var(--t-pyh) + var(--t-hzlh));
  --page-w: {pw}mm; --pad: {mv}mm {mh}mm;
  --vgap: {cfg['vgap']:.2f}; --lgap: {cfg['lgap']:.2f};
  --fh: {FONT_STACKS[cfg['font']]};
}}
:root {{ --fh: {FONT_STACKS[cfg['font']]}; }}
"""


def render_document(spec: dict, ann: Annotation, ann_title, ann_author,
                    out_path: Path) -> dict:
    """渲染完整 HTML 文档，写入 out_path；返回版面信息。"""
    template = spec.get("_template")
    if template not in TEMPLATES:
        raise RenderError(f"未知模板 {template}")
    cfg = resolve_config(spec, template)

    pw, _ph = PAGE_SIZES[cfg["page"]]
    if cfg["landscape"]:
        pw = PAGE_SIZES[cfg["page"]][1]
    _mv, mh = cfg["margin_mm"]
    content_pt = (pw - 2 * mh) / 25.4 * 72.0

    verse_like = _is_verse_like(ann)
    cfg["_has_title"] = bool(spec.get("title"))
    cfg["_has_author"] = bool(spec.get("author") or spec.get("dynasty"))
    if template == "reading" or (template == "worksheet" and not verse_like):
        fs, cell_r, units = cfg["han_size"], max(
            1.22, _max_pinyin_len(ann) * cfg["pinyin_ratio"] * 0.52 + 0.14), 12.0
        wrap = False
    else:
        fs, cell_r, units, wrap = _fit_han_size(cfg, ann)

    header, t_scale = build_header(
        spec.get("title") or "", ann_title,
        spec.get("author") or "", spec.get("dynasty") or "", ann_author,
        cfg, fs, content_pt)

    if template == "poem":
        body = build_poem_body(ann, cfg, fs=fs, wrap=wrap)
    elif template == "reading":
        body = build_reading_body(ann, cfg)
    elif verse_like:
        body = build_poem_body(ann, cfg, fs=fs, tian=cfg["copy_rows"] > 0, wrap=wrap)
    else:
        body = build_reading_body(ann, cfg)

    footer = (f'<div class="py-note">{_html.escape(str(cfg["footer"]))}</div>'
              if cfg["footer"] else "")

    tpl = (_TPL_DIR / f"{template}.html").read_text(encoding="utf-8")
    common_css = (_TPL_DIR / "base.css").read_text(encoding="utf-8")
    page_css = _page_css(cfg)
    css_vars = _css_vars(cfg, fs, cell_r, units, t_scale)
    clamp = template in ("poem", "worksheet") and verse_like
    body_class = (
        f"mode-{cfg['mode']} tpl-{template}"
        f"{' auto-clamp' if clamp else ''}{' wrap-ok' if wrap else ''}"
        f"{' cols-2' if cfg['columns'] == 2 else ''}")

    doc = (tpl
           .replace("{{common_css}}", page_css + css_vars + common_css)
           .replace("{{title}}", _html.escape(spec.get("title") or "注音文档"))
           .replace("{{body_class}}", body_class)
           .replace("{{header}}", header)
           .replace("{{stanzas}}", body)
           .replace("{{paragraphs}}", body)
           .replace("{{body}}", body)
           .replace("{{footer}}", footer)
           .replace("{{spec_json}}", json.dumps(
               spec, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")))

    out_path.write_text(doc, encoding="utf-8", newline="\n")
    return {
        "template": template,
        "mode": cfg["mode"],
        "columns": cfg["columns"],
        "han_size": round(fs, 2),
        "pinyin_size": round(fs * cfg["pinyin_ratio"], 2),
        "page": cfg["page"],
        "cell_ratio": round(cell_r, 3),
        "verse_like": verse_like,
        "clause_wrap": wrap,
        "output": str(out_path),
    }


def _is_verse_like(ann: Annotation) -> bool:
    """正文是否像诗行（行短居中）→ 用诗行排版（单句/两句一行都算）。"""
    lines = [toks for toks in ann.lines if toks]
    return bool(lines) and max(_line_units(toks, 1.3) for toks in lines) <= 20


def extract_spec_from_html(path: Path) -> dict:
    """从生成的 HTML 中恢复 spec（供改读音/改样式后重新生成）。"""
    m = re.search(
        r'<script type="application/json" id="cpt-spec">(.*?)</script>',
        path.read_text(encoding="utf-8"), re.S)
    if not m:
        raise RenderError(f"{path} 中未找到嵌入的 spec（可能不是本 Skill 生成的文件）")
    raw = m.group(1).replace("<\\/", "</")
    return json.loads(raw)
