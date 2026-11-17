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
        "couplet": spec.get("couplet", "auto"),
        "target_pages": spec.get("target_pages", 0),
    }
    # 记录边距/行距是否用户显式指定：页数目标的自动收缩只动未指定的项
    cfg["_margin_set"] = spec.get("margin_mm") is not None
    cfg["_gap_set"] = spec.get("line_gap_scale") is not None
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
    if not isinstance(cfg["couplet"], (bool, str)) or \
            (isinstance(cfg["couplet"], str) and cfg["couplet"] not in ("auto", "")):
        raise RenderError("couplet 需为 true/false/auto（是否一联一行合并排版）")
    try:
        cfg["target_pages"] = int(cfg["target_pages"] or 0)
    except (TypeError, ValueError):
        raise RenderError(f"target_pages 需为正整数（当前 {cfg['target_pages']!r}）")
    if not (0 <= cfg["target_pages"] <= 50):
        raise RenderError("target_pages 需为 1-50 之间的页数目标（省略则自动）")
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


# ---------------------------------------------------------------------------
# 版面计算：小句 → 展示行 → 策略求解与选择
#
# 层级：源行（原文一行）—小句（句读处拆分）—展示行（实际排成一行的内容）。
# 两种展示策略：
#   pair=False（S1 舒展）：一小句一行，绝句/律诗竖版教材风；
#   pair=True （S2 紧凑）：同一源行内的小句按宽度预算贪心合并（通常一联一行，
#                          三字句等短句可 3-4 句一行），绝不跨源行、绝不拆小句。
# 所有高度都是 fs 的线性函数，可直接解字号上限。
# ---------------------------------------------------------------------------

PAIR_BUDGET_HAN = 8.0   # 合并宽度预算：两个 8 字小句（含句读）以内允许同行

FIT_FLOOR_K = 0.55      # 默认模式字号下限 = max(han_size×该系数, ABS_MIN_FS)
ABS_MIN_FS = 10.0       # 页数目标模式的绝对字号下限（拼音约 5.5pt，不再更低）
COMFORT_K = 0.45        # 页数目标模式的期望字号 = max(han_size×该系数, COMFORT_MIN_FS)
COMFORT_MIN_FS = 12.0
MARGIN_SCALES = (1.0, 0.85, 0.72)   # 页数目标下的边距自动收窄档位
MARGIN_MIN_MM = 12.0
GAP_SCALES = (1.0, 0.85, 0.7)       # 页数目标下的行距自动收紧档位
GAP_MIN = 0.3


def _stanza_fragments(ann: Annotation) -> list[list[list[Token]]]:
    """返回 [节][源行][小句 tokens]。小句 = _split_verse 在句读处拆出的"一句"。"""
    return [[_split_verse(toks) for toks in stanza] for stanza in _stanzas(ann)]


def _pair_budget(cell_r: float) -> float:
    """合并宽度预算（units）：约两个七言小句，随拼音长度自适应。"""
    return 2.0 * (PAIR_BUDGET_HAN * cell_r + 0.56)


def _display_lines(line_frags: list[list[Token]], cell_r: float,
                   pair: bool) -> list[list[Token]]:
    """源行的小句序列 → 展示行（token 列表）。

    pair=False：一小句一行；pair=True：源行内贪心合并到宽度预算，
    放不下即换行；单小句超预算独占一行。小句永不拆开、源行间永不合并。
    """
    if not pair:
        return [list(f) for f in line_frags]
    budget = _pair_budget(cell_r)
    rows: list[list[Token]] = []
    cur: list[Token] = []
    cur_u = 0.0
    for frag in line_frags:
        u = _line_units(frag, cell_r)
        if cur and cur_u + u > budget:
            rows.append(cur)
            cur, cur_u = [], 0.0
        cur.extend(frag)
        cur_u += u
    if cur:
        rows.append(cur)
    return rows


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


def _page_geometry(cfg: dict, margin_scale: float = 1.0) -> tuple[float, float]:
    """返回 (内容宽 pt, 内容高 pt)；margin_scale 只作用于未显式指定的边距档位。"""
    pw, ph = PAGE_SIZES[cfg["page"]]
    if cfg["landscape"]:
        pw, ph = ph, pw
    mv, mh = cfg["margin_mm"]
    mv = max(mv * margin_scale, MARGIN_MIN_MM) if margin_scale < 1.0 else mv
    mh = max(mh * margin_scale, MARGIN_MIN_MM) if margin_scale < 1.0 else mh
    return (pw - 2 * mh) / 25.4 * 72.0, (ph - 2 * mv) / 25.4 * 72.0


def _layout_metrics(cfg: dict, ann: Annotation, cell_r: float, pair: bool,
                    content_w: float, content_h: float) -> dict:
    """一个策略 + 一组页面几何下的求解。

    返回 {rows_per_stanza, dl_stanzas, max_units, header_k, body_k,
          fs_w, fs_v, fs, total_h}；高度类均为 fs 的倍数（_k 后缀）。
    """
    cols = cfg["columns"]
    dl_stanzas = [
        [row for lf in st for row in _display_lines(lf, cell_r, pair)]
        for st in _stanza_fragments(ann)
    ]
    rows_per_stanza = [len(dl) for dl in dl_stanzas] or [1]
    max_units = max(
        (u for dl in dl_stanzas for u in [_line_units(r, cell_r) for r in dl]),
        default=cell_r)
    fs_w = content_w / max(cols * max_units + COLUMN_GAP_K * (cols - 1), 0.5)

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
    body_k = max(
        rows * (row_k + cfg["vgap"]) - cfg["vgap"] + max(st - 1, 0) * 1.6 + rows * tian_k
        for rows, st in _pack_columns(rows_per_stanza, cols)
    )
    target = cfg.get("target_pages", 0)
    if target >= 1:
        # 每个额外分页断点最多浪费一行高度（保守计入）
        slack_k = (target - 1) * (row_k + cfg["vgap"])
        fs_v = target * content_h / max(header_k + body_k + slack_k, 1.0)
    else:
        fs_v = content_h / max(header_k + body_k, 1.0)
    fs = min(cfg["han_size"], fs_w, fs_v)
    total_h = (header_k + body_k) * fs                # 无分页损耗的估算总高
    return {"rows_per_stanza": rows_per_stanza, "dl_stanzas": dl_stanzas,
            "max_units": max_units, "header_k": header_k, "body_k": body_k,
            "fs_w": fs_w, "fs_v": fs_v, "fs": fs, "total_h": total_h,
            "content_h": content_h}


def _cell_ratio(cfg: dict, ann: Annotation) -> float:
    if cfg["mode"] == "hanzi":
        return 1.12
    return max(1.22, _max_pinyin_len(ann) * cfg["pinyin_ratio"] * 0.52 + 0.14)


def _choose_verse_layout(cfg: dict, ann: Annotation) -> dict:
    """诗行排版决策：策略（一小句一行 / 源行内合并）+ 字号 + 页数目标求解。

    couplet=false/true 直接锁定策略；auto 时：
      - 有 target_pages：在（策略×边距档×行距档）组合里选「达到页数目标且
        字号 ≥ 舒适下限」的最大字号方案；全部达不到 → 放宽到绝对下限 10pt
        并取页数最少者（如实 warning，不无限缩字）。
      - 无 target_pages：单页放得下且不触底的策略优先（S1 舒展优先）；
        都触底 → 取纵向字号上限更大（欠缩更少）者，长诗自然分页。
    选定后把边距/行距调整写回 cfg（_css_vars/_page_css 直接使用）。
    """
    cell_r = _cell_ratio(cfg, ann)
    target = cfg.get("target_pages", 0)
    couplet = cfg.get("couplet", "auto")
    pairs = [bool(couplet)] if isinstance(couplet, bool) else [False, True]

    def solve(pair: bool, ms: float = 1.0, gs: float = 1.0) -> dict:
        trial = dict(cfg)
        if ms < 1.0 or gs < 1.0:
            trial["vgap"] = max(cfg["vgap"] * gs, GAP_MIN)
            trial["lgap"] = max(cfg["lgap"] * gs, GAP_MIN)
        content_w, content_h = _page_geometry(trial, ms)
        return _layout_metrics(trial, ann, cell_r, pair, content_w, content_h)

    if target >= 1:
        comfort = max(cfg["han_size"] * COMFORT_K, COMFORT_MIN_FS)
        m_scales = MARGIN_SCALES if not cfg.get("_margin_set") else (1.0,)
        g_scales = GAP_SCALES if not cfg.get("_gap_set") else (1.0,)
        # tier 0 = 字号≥舒适下限；tier 1 = 只到绝对下限。先 tier 后字号，
        # 再少收缩边距/行距，最后偏舒展策略（pair=False）。
        cands = []
        for pair in pairs:
            for ms in m_scales:
                for gs in g_scales:
                    m = solve(pair, ms, gs)
                    if m["fs"] < ABS_MIN_FS or \
                            m["total_h"] > target * m["content_h"] + 0.5:
                        continue
                    tier = 0 if m["fs"] >= comfort else 1
                    cands.append((tier, -m["fs"], ms, gs, pair is False,
                                  (ms, gs, pair), m))
        if cands:
            best = min(cands, key=lambda x: x[:5])
            fs, (ms, gs, pair), m = best[1] * -1, best[5], best[6]
        else:
            # 绝对下限也放不下：字号钳到绝对下限，取页数最少者（如实报告）
            pool = []
            for pair in pairs:
                for ms in m_scales:
                    for gs in g_scales:
                        m = solve(pair, ms, gs)
                        fs_use = max(m["fs"], ABS_MIN_FS)
                        pages = max(1, math.ceil(
                            (m["header_k"] + m["body_k"]) * fs_use / m["content_h"] - 1e-6))
                        pool.append((pages, -fs_use, (ms, gs, pair), m, fs_use))
            b = min(pool, key=lambda x: (x[0], x[1]))
            fs, (ms, gs, pair), m = b[4], b[2], b[3]
        plan = {"pair": pair, "fs": fs, "cell_r": cell_r, "units": m["max_units"],
                "metrics": m, "target": target,
                "margin_scale": ms, "gap_scale": gs}
    else:
        floor = max(cfg["han_size"] * FIT_FLOOR_K, ABS_MIN_FS)
        cands = []
        for pair in pairs:
            m = solve(pair)
            fs = m["fs"] if m["fs"] >= floor else floor   # 触底钳到下限，超页自然分页
            cands.append({"pair": pair, "fs": fs, "m": m})
        # 单页放得下且不触底 → 字号大者优先（平局取 S1 舒展）；都触底 → 纵向上限大者
        ok = [c for c in cands if c["fs"] == c["m"]["fs"]]
        if ok:
            best = max(ok, key=lambda c: (c["fs"], c["pair"] is False))
        else:
            best = max(cands, key=lambda c: (c["m"]["fs_v"], c["pair"] is False))
        pair, fs, m = best["pair"], best["fs"], best["m"]
        plan = {"pair": pair, "fs": fs, "cell_r": cell_r, "units": m["max_units"],
                "metrics": m, "target": 0, "margin_scale": 1.0, "gap_scale": 1.0}

    wrap = fs > m["fs_w"] + 0.01                   # 字号超宽度上限 → 放行句读处折行
    plan["wrap"] = wrap
    total_k = m["header_k"] + m["body_k"]          # 高度总系数（fs 的倍数）
    plan["pages_est"] = max(1, math.ceil(total_k * fs / m["content_h"] - 1e-6))
    plan["rows_per_stanza"] = m["rows_per_stanza"]
    # 写回边距/行距调整（_css_vars / _page_css 使用）
    if plan["margin_scale"] < 1.0:
        mv, mh = cfg["margin_mm"]
        cfg["margin_mm"] = (max(mv * plan["margin_scale"], MARGIN_MIN_MM),
                            max(mh * plan["margin_scale"], MARGIN_MIN_MM))
    if plan["gap_scale"] < 1.0:
        cfg["vgap"] = max(cfg["vgap"] * plan["gap_scale"], GAP_MIN)
        cfg["lgap"] = max(cfg["lgap"] * plan["gap_scale"], GAP_MIN)
    return plan


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


def build_poem_body(ann: Annotation, cfg: dict, plan: dict, *, tian: bool = False) -> str:
    """诗行正文：按 plan 的展示行输出 .v 行。

    每节按几何判定：节高 ≤ 页内容高 → 默认 keep（break-inside:avoid，节不跨页）；
    超高节 → 追加 flow 类（允许在展示行边界自然分页，.v 自身原子、一联不拆）。
    田字格行与所属诗句包 .vgrp（书写行不与诗句分离）。
    """
    out = []
    fs = plan["fs"]
    row_k = cfg["pinyin_ratio"] * 1.7 + 1.18
    tian_k = 2.0 * cfg["copy_rows"] if cfg["copy_rows"] else 0.0
    content_h = plan["metrics"]["content_h"]
    header_k = plan["metrics"]["header_k"]
    for i, dl in enumerate(plan["metrics"]["dl_stanzas"]):
        items: list[str] = []
        for row in dl:
            v = line_cells(row, cfg["mode"], poem=True, allow_break=plan["wrap"])
            if tian:
                n = sum(1 for t in row if t.is_han)
                grp = f'<div class="v">{v}</div>' + _tian_row(n, wrap=n > 18)
                items.append(f'<div class="vgrp">{grp}</div>')
            else:
                items.append(f'<div class="v">{v}</div>')
        stanza_k = len(dl) * (row_k + cfg["vgap"] + tian_k) - cfg["vgap"]
        # 第一节 keep 还须连同标题块放进首页：否则整节后移会让标题孤立成页
        budget_k = stanza_k + (header_k if i == 0 else 0.0)
        cls = "stanza" if budget_k * fs <= content_h + 0.5 else "stanza flow"
        out.append(f'<div class="{cls}">{"".join(items)}</div>')
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

    verse_like = _is_verse_like(ann)
    cfg["_has_title"] = bool(spec.get("title"))
    cfg["_has_author"] = bool(spec.get("author") or spec.get("dynasty"))
    if template == "reading" or (template == "worksheet" and not verse_like):
        plan = None
        fs, cell_r, units = cfg["han_size"], max(
            1.22, _max_pinyin_len(ann) * cfg["pinyin_ratio"] * 0.52 + 0.14), 12.0
        wrap = False
    else:
        # 排版决策先行：可能收窄边距/行距，后续标题宽度与 CSS 变量都取调整后值
        plan = _choose_verse_layout(cfg, ann)
        fs, cell_r, units, wrap = plan["fs"], plan["cell_r"], plan["units"], plan["wrap"]

    pw2 = PAGE_SIZES[cfg["page"]][0]
    if cfg["landscape"]:
        pw2 = PAGE_SIZES[cfg["page"]][1]
    _mv2, mh2 = cfg["margin_mm"]
    content_pt = (pw2 - 2 * mh2) / 25.4 * 72.0

    header, t_scale = build_header(
        spec.get("title") or "", ann_title,
        spec.get("author") or "", spec.get("dynasty") or "", ann_author,
        cfg, fs, content_pt)

    if plan is None:
        body = build_reading_body(ann, cfg)
    elif template == "poem":
        body = build_poem_body(ann, cfg, plan)
    elif verse_like:
        body = build_poem_body(ann, cfg, plan, tian=cfg["copy_rows"] > 0)
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
        f"{' pair' if plan is not None and plan['pair'] else ''}"
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
    layout = {
        "strategy": ("flow" if plan is None else ("couplet" if plan["pair"] else "clause")),
        "pages_est": (plan["pages_est"] if plan is not None else None),
        "target_pages": cfg["target_pages"] or None,
        "margin_mm": [round(v, 1) for v in cfg["margin_mm"]],
        "line_gap_scale": round(cfg["vgap"], 2),
    }
    if plan is not None and cfg["target_pages"] and plan["pages_est"] > cfg["target_pages"]:
        layout["target_met"] = False
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
        "layout": layout,
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
