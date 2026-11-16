# -*- coding: utf-8 -*-
"""渲染层单元测试：HTML 结构、自包含性、模式切换、spec 回读、
CLI 端到端（含 --from-html 再生成）。浏览器级排版检查见 browser_check.py。"""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import pronunciation as pr  # noqa: E402
import renderer as rd  # noqa: E402

JYS = "床前明月光，疑是地上霜。\n举头望明月，低头思故乡。"
TMP = Path(__file__).resolve().parent / "_tmp"
TMP.mkdir(exist_ok=True)


def make(spec: dict, name="out.html") -> Path:
    spec = dict(spec)
    spec.setdefault("_template", spec.get("template", "poem") if spec.get("template") != "auto" else "poem")
    ann = pr.annotate(spec["text"], overrides=spec.get("overrides"))
    out = TMP / name
    rd.render_document(spec, ann, None, None, out)
    return out


def run_cli(*args) -> dict:
    r = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPTS / "generate.py"), *args],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=str(TMP), timeout=120)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {"ok": False, "error": f"rc={r.returncode} stdout={r.stdout[:300]} stderr={r.stderr[:300]}"}


def test_selfcontained_html():
    out = make({"title": "静夜思", "author": "李白", "text": JYS}, "a.html")
    doc = out.read_text(encoding="utf-8")
    assert doc.startswith("<!doctype html>") and 'charset="utf-8"' in doc
    assert "<style>" in doc and "@page" in doc and "size: A4" in doc
    assert "http://" not in doc.replace("http://www.w3.org", "")  # 无外部资源
    assert "src=" not in doc and "@import" not in doc
    assert 'id="cpt-spec"' in doc                     # 内嵌 spec 供再生成


def test_ruby_structure_and_alignment_css():
    out = make({"title": "静夜思", "text": JYS}, "b.html")
    doc = out.read_text(encoding="utf-8")
    assert doc.count("<ruby") == pr.annotate(JYS).hanzi_count + 4  # 正文汉字+句读标点（make 标题未注音）
    assert "inline-flex" in doc and "column-reverse" in doc        # 非默认 ruby 排版
    assert re.search(r'<rt class="y">chuáng</rt>', doc)            # 声调完整
    assert doc.count('class="c p tuck"') == 4                      # 4 个句读收窄


def test_modes_share_same_annotation_data():
    doc_both = make({"title": "静夜思", "text": JYS, "mode": "both"}, "c1.html").read_text(encoding="utf-8")
    doc_hanzi = make({"title": "静夜思", "text": JYS, "mode": "hanzi"}, "c2.html").read_text(encoding="utf-8")
    doc_py = make({"title": "静夜思", "text": JYS, "mode": "pinyin"}, "c3.html").read_text(encoding="utf-8")
    doc_blank = make({"title": "静夜思", "text": JYS, "mode": "blank_pinyin"}, "c4.html").read_text(encoding="utf-8")
    assert "mode-hanzi" in doc_hanzi and '<rt' not in re.sub(r'<rt class="y"></rt>', '', doc_hanzi)
    assert doc_py.count('class="tz"') == 20              # 正文 20 字（标题未注音）
    assert 'y blank' in doc_blank
    assert "chuáng" in doc_both and "chuáng" in doc_py   # 同一份注音数据


def test_one_verse_per_line_and_stanza_groups():
    out = make({"title": "静夜思", "text": JYS}, "d.html")
    doc = out.read_text(encoding="utf-8")
    assert doc.count('<div class="v">') == 4             # 两句一行 → 四句四行
    assert doc.count('<div class="stanza">') == 1        # 连续两行为一节（空行分节）


def test_reading_template_keeps_paragraphs():
    text = "外婆的小菜园在屋后的坡地上，一年四季都热热闹闹。\n\n春天，韭菜先冒出尖尖的绿芽。\n2024 年 10 月 1 日。"
    out = make({"title": "课文", "text": text, "template": "reading"}, "e.html")
    doc = out.read_text(encoding="utf-8")
    assert doc.count('<p class="para">') == 3            # 空行分段保留
    assert doc.count('class="nb"') >= 3                  # 避头尾分组


def test_flow_clusters_bind_punctuation():
    """流式正文聚类：闭合标点并入前簇（连续闭合同簇）、开启标点并入后簇、
    簇内零断点、<wbr> 只在簇间。"""
    text = '他说：“你好。”然后（继续）走了。'
    out = make({"title": "课", "text": text, "template": "reading"}, "cluster.html")
    doc = out.read_text(encoding="utf-8")
    para = re.search(r'<p class="para">(.*?)</p>', doc, re.S).group(1)
    nbs = re.findall(r'<span class="nb">((?:<ruby.*?</ruby>)+)</span>', para, re.S)
    assert nbs, "未生成任何 .nb 簇"
    assert all("<wbr>" not in nb for nb in nbs)        # 簇内绝无断点
    seqs = [re.findall(r'<span class="h">(.*?)</span>', nb) for nb in nbs]
    assert ["好", "。", "”"] in seqs                    # 连续闭合标点（。”）与汉字同簇
    assert any(sq[:2] == ["（", "继"] for sq in seqs)   # 开启标点绑定后续汉字
    assert ["了", "。"] in seqs and ["续", "）"] in seqs
    assert ["说", "："] in seqs                         # 冒号并入前字
    # 10 个簇 → 簇间恰好 9 个 wbr（无空白分隔时）
    assert para.count("<wbr>") == 9
    # 旧缺陷的语义特征不得再现：任何 .nb 都必须包含内容单元（汉字/拉丁），
    # 不允许只包标点
    assert all(re.search(r'<ruby class="c(?: lat)?">', nb) for nb in nbs)


def test_first_line_indent_two_han():
    doc = make({"title": "课", "text": "外婆的小菜园在屋后的坡地上，一年四季都热热闹闹。", "template": "reading"},
               "ind1.html").read_text(encoding="utf-8")
    assert "text-indent: calc(var(--cell) * 2)" in doc    # 缩进=2 个注音格
    ws = make({"title": "练习",
               "text": "这是一段足够长的现代课文句子，用来触发流式排版而不是诗行排版。" * 3,
               "template": "worksheet"}, "ind2.html").read_text(encoding="utf-8")
    assert "text-indent: calc(var(--cell) * 2)" in ws     # worksheet 阅读流同样缩进
    poem = make({"title": "静夜思", "text": JYS}, "ind3.html").read_text(encoding="utf-8")
    assert "text-indent" not in poem                    # 诗行居中，不缩进


def test_worksheet_tian_rows_and_meta():
    out = make({"title": "山行", "text": "远上寒山石径斜，白云生处有人家。",
                "template": "worksheet", "mode": "pinyin"}, "f.html")
    doc = out.read_text(encoding="utf-8")
    assert "姓名" in doc and "日期" in doc and "得分" in doc
    assert doc.count('class="tian-row"') == 2            # 每句一行书写格
    assert '<div class="ws-meta">' in doc


def test_fit_shrinks_for_long_verse():
    long_line = "飞流直下三千尺" * 4 + "！"
    out = make({"title": "长句", "text": long_line}, "g.html")
    doc = out.read_text(encoding="utf-8")
    fs = float(re.search(r"--fs-base: ([\d.]+)pt", doc).group(1))
    assert fs < 32
    long_long = "曲" * 50           # 宽度解低于绝对下限 → floor + 字间折行兜底
    out2 = make({"title": "超长", "text": long_long}, "g2.html")
    doc2 = out2.read_text(encoding="utf-8")
    assert "wrap-ok" in doc2                            # 超长句放行折行


def test_spec_roundtrip_from_html():
    out = make({"title": "回乡偶书", "author": "贺知章", "dynasty": "唐",
                "text": "乡音无改鬓毛衰。",
                "overrides": [{"index": 6, "pinyin": "cuī"}]}, "h.html")
    spec = rd.extract_spec_from_html(out)
    assert spec["title"] == "回乡偶书"
    assert spec["overrides"] == [{"index": 6, "pinyin": "cuī"}]
    # spec 中的正文与原文一致（不被注音过程污染）
    assert spec["text"] == "乡音无改鬓毛衰。"


def test_cli_text_parse_and_review_output():
    spec = TMP / "cli1.json"
    spec.write_text(json.dumps({
        "title": "回乡偶书", "author": "贺知章",
        "text": "乡音无改鬓毛衰。\n儿童相见不相识。"}, ensure_ascii=False), encoding="utf-8")
    r = run_cli("--spec", spec.name, "--out", "cli1.html")
    assert r["ok"], r
    assert r["hanzi_count"] == 14
    assert any(n.startswith("统编教材") for n in r["notes"])
    assert any(x["char"] == "衰" for x in r["review"])


def test_cli_from_html_regeneration_with_override():
    first = run_cli("--spec", write_spec(TMP / "cli2.json", {
        "title": "静夜思", "text": JYS}), "--out", "cli2.html")
    assert first["ok"], first
    r = run_cli("--from-html", "cli2.html",
                "--override", '{"line":2,"char":2,"tone":4}',
                "--set", "mode=hanzi", "--out", "cli3.html")
    assert r["ok"], r
    assert r["mode"] == "hanzi"
    assert r["overrides_applied"] and r["overrides_applied"][0]["chars"] == "头"
    doc = (TMP / "cli3.html").read_text(encoding="utf-8")
    assert 'mode-hanzi' in doc
    spec = rd.extract_spec_from_html(TMP / "cli3.html")
    assert {"line": 2, "char": 2, "tone": 4} in spec["overrides"]  # 改动持久进嵌入 spec


def write_spec(path: Path, spec: dict) -> str:
    path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    return path.name


def test_cli_auto_template_and_textfile():
    tf = TMP / "poem.txt"
    tf.write_text("《静夜思》\n李白\n床前明月光，疑是地上霜。\n举头望明月，低头思故乡。",
                  encoding="utf-8")
    r = run_cli("--text-file", tf.name, "--out", "cli4.html")
    assert r["ok"] and r["template"] == "poem", r
    doc = (TMP / "cli4.html").read_text(encoding="utf-8")
    assert "李白" in doc
    tf2 = TMP / "prose.txt"
    tf2.write_text("这是一段比较长的现代课文，" * 10, encoding="utf-8")
    r2 = run_cli("--text-file", tf2.name, "--out", "cli5.html")
    assert r2["ok"] and r2["template"] == "reading", r2


def test_cli_from_html_phrase_all_roundtrip():
    """端到端：--from-html + phrase+all 纠音（原缺陷的 CLI 复现路径）。"""
    first = run_cli("--spec", write_spec(TMP / "cli8.json", {
        "title": "课", "text": "厌恶黑夜，也厌恶寒冷。"}), "--out", "cli8.html")
    assert first["ok"], first
    r = run_cli("--from-html", "cli8.html",
                "--override", '{"phrase":"厌恶","pinyin":"yàn wù","all":true}',
                "--out", "cli9.html")
    assert r["ok"], r
    assert r["overrides_applied"][0]["chars"] == "厌恶厌恶"
    spec = rd.extract_spec_from_html(TMP / "cli9.html")
    assert {"phrase": "厌恶", "pinyin": "yàn wù", "all": True} in spec["overrides"]
    doc = (TMP / "cli9.html").read_text(encoding="utf-8")
    assert doc.count("<rt class=\"y\">yàn</rt>") == 2   # 两处均改
    assert doc.count("<rt class=\"y\">wù</rt>") >= 2


def test_cli_errors_exit_code_2():
    r = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPTS / "generate.py"),
                        "--spec", "no_such.json"], capture_output=True,
                       text=True, encoding="utf-8", cwd=str(TMP))
    assert r.returncode == 2
    assert json.loads(r.stdout)["ok"] is False


def test_output_default_name_by_mode():
    r = run_cli("--spec", write_spec(TMP / "cli6.json", {
        "title": "春晓", "text": "春眠不觉晓，处处闻啼鸟。"}))
    assert r["ok"]
    assert Path(r["output"]).name.startswith("春晓")
    r2 = run_cli("--spec", write_spec(TMP / "cli7.json", {
        "title": "春晓", "text": "春眠不觉晓，处处闻啼鸟。", "mode": "hanzi"}))
    assert "背诵版" in Path(r2["output"]).name


def test_render_rejects_bad_config():
    with pytest.raises(rd.RenderError):
        make({"text": JYS, "mode": "nope"}, "bad1.html")
    with pytest.raises(rd.RenderError):
        make({"text": JYS, "page": "B4"}, "bad2.html")
    with pytest.raises(rd.RenderError):
        make({"text": JYS, "han_size": 500}, "bad3.html")


def test_columns_two_layout():
    """columns=2：body 加 cols-2 类、CSS 双栏生效、字号按半栏宽求解（小于单栏）。"""
    doc2 = make({"title": "静夜思", "text": JYS, "columns": 2}, "col1.html").read_text(encoding="utf-8")
    doc1 = make({"title": "静夜思", "text": JYS}, "col2.html").read_text(encoding="utf-8")
    body2 = re.search(r'<body class="([^"]*)"', doc2).group(1)
    body1 = re.search(r'<body class="([^"]*)"', doc1).group(1)
    assert "cols-2" in body2 and "column-count: 2" in doc2
    assert "cols-2" not in body1                             # 默认单栏
    fs2 = float(re.search(r"--fs-base: ([\d.]+)pt", doc2).group(1))
    fs1 = float(re.search(r"--fs-base: ([\d.]+)pt", doc1).group(1))
    assert fs2 < fs1                                           # 半栏宽 → 字号上限更低
    # 窄屏回退单栏（仅屏幕）与栏间距系数在 CSS 中成对出现
    assert "column-count: 1" in doc2
    assert "column-gap: calc(var(--fs) * 2.5)" in doc2
    # reading 模板同样支持双栏
    docr = make({"title": "课", "text": "这是一段比较长的现代课文句子，" * 6,
                 "template": "reading", "columns": 2}, "col3.html").read_text(encoding="utf-8")
    assert "cols-2" in docr and "tpl-reading" in docr


def test_columns_validation():
    with pytest.raises(rd.RenderError):
        make({"text": JYS, "columns": 3}, "colbad1.html")
    with pytest.raises(rd.RenderError):
        make({"text": JYS, "columns": "two"}, "colbad2.html")


def test_columns_cli_roundtrip():
    """CLI：spec columns=2 → 摘要回显；--from-html 可改回单栏。"""
    r = run_cli("--spec", write_spec(TMP / "cli10.json", {
        "title": "春晓", "text": "春眠不觉晓，处处闻啼鸟。\n夜来风雨声，花落知多少。",
        "columns": 2}), "--out", "cli10.html")
    assert r["ok"]
    assert r["columns"] == 2
    doc = (TMP / "cli10.html").read_text(encoding="utf-8")
    assert "cols-2" in doc
    assert rd.extract_spec_from_html(TMP / "cli10.html")["columns"] == 2
    r2 = run_cli("--from-html", "cli10.html", "--set", "columns=1", "--out", "cli11.html")
    assert r2["ok"] and r2["columns"] == 1
    body1 = re.search(r'<body class="([^"]*)"', (TMP / "cli11.html").read_text(encoding="utf-8")).group(1)
    assert "cols-2" not in body1


# ---------------------------------------------------------------------------
# 自适应排版决策（v1.3.0）：一联一行 / 页数目标 / 分页结构
# ---------------------------------------------------------------------------

LSLV = ("昔人已乘黄鹤去，此地空余黄鹤楼。\n黄鹤一去不复返，白云千载空悠悠。\n"
        "晴川历历汉阳树，芳草萋萋鹦鹉洲。\n日暮乡关何处是，烟波江上使人愁。")


def make_info(spec: dict, name: str):
    spec = dict(spec)
    spec.setdefault("_template", spec.get("template", "poem")
                   if spec.get("template") != "auto" else "poem")
    ann = pr.annotate(spec["text"], overrides=spec.get("overrides"))
    out = TMP / name
    info = rd.render_document(spec, ann, None, None, out)
    return info, out.read_text(encoding="utf-8")


def test_couplet_true_merges_within_source_line():
    """couplet=true：同一源行的两个小句合并为一行（一联一行），源行边界保留。"""
    info, doc = make_info({"title": "静夜思", "text": JYS, "couplet": True}, "cp1.html")
    assert info["layout"]["strategy"] == "couplet"
    assert doc.count('<div class="v">') == 2            # 2 源行 → 2 展示行
    first = re.search(r'<div class="v">(.*?)</div>', doc, re.S).group(1)
    # 一行含 10 个汉字单元 + 2 个句读单元；句读保留在句尾（不落行首）
    assert len(re.findall(r'<span class="h">[床前明月光疑是地上霜]</span>', first)) == 10
    assert first.count('class="c p tuck"') == 2


def _han_of(fragment_html: str) -> str:
    return "".join(re.findall(r'<span class="h">([^<]*)</span>', fragment_html))


def test_couplet_never_merges_across_source_lines():
    """两个源行各含两个小句：合并只在源行内，跨行不合并，顺序保持。"""
    text = "白日依山尽，黄河入海流。\n欲穷千里目，更上一层楼。"
    _, doc = make_info({"title": "登鹳雀楼", "text": text, "couplet": True}, "cp2.html")
    assert doc.count('<div class="v">') == 2
    vs = re.findall(r'<div class="v">(.*?)</div>', doc, re.S)
    assert _han_of(vs[0]) == "白日依山尽，黄河入海流。"
    assert _han_of(vs[1]) == "欲穷千里目，更上一层楼。"


def test_couplet_true_merges_long_source_line_within_floor():
    """couplet=true：联行优先于大字号——超长源行（如"君不见…"19 字）整体
    一行，字号可缩但不低于默认下限（floor=han_size×0.55）。"""
    text = "君不见黄河之水天上来，奔流到海不复回。"
    info, doc = make_info({"title": "将进酒(节)", "text": text, "couplet": True}, "cp3.html")
    assert info["layout"]["strategy"] == "couplet"
    assert doc.count('<div class="v">') == 1            # 整源行一行
    assert info["han_size"] >= 32 * 0.55                # 字号不破下限


def test_auto_leaves_overlong_clause_alone():
    """auto：贪心按宽度组织——超预算的长短句自然独占一行，不为合并缩字。"""
    text = "君不见黄河之水天上来，奔流到海不复回。"
    info, doc = make_info({"title": "将进酒(节)", "text": text}, "cp3b.html")
    vs = re.findall(r'<div class="v">(.*?)</div>', doc, re.S)
    assert len(vs) == 2                                  # 两小句各自成行
    assert _han_of(vs[0]) == "君不见黄河之水天上来，"
    assert info["han_size"] > 32 * 0.55 * 1.5            # 未过度缩字


def test_auto_spacious_for_short_poem_compact_for_long():
    """auto 决策：绝句保持一句一行（字号更大）；长诗自动联行。"""
    info_short, doc_short = make_info({"title": "静夜思", "text": JYS}, "au1.html")
    assert info_short["layout"]["strategy"] == "clause"
    assert doc_short.count('<div class="v">') == 4
    long_text = "\n".join("春江潮水连海平，海上明月共潮生。" for _ in range(9))
    info_long, doc_long = make_info({"title": "春江花月夜(节选)", "text": long_text}, "au2.html")
    assert info_long["layout"]["strategy"] == "couplet"
    assert doc_long.count('<div class="v">') < 18       # 18 小句合并为 9 行
    assert info_long["han_size"] >= 17.6                # 未低于默认触底字号


def test_target_pages_shrinks_to_fit_one_page():
    """target_pages=1：字号/边距/行距联合求解，估算 1 页且字号不跌破下限。"""
    long_text = "\n".join("春江潮水连海平，海上明月共潮生。" for _ in range(9))
    info, doc = make_info({"title": "春江", "text": long_text, "target_pages": 1}, "tp1.html")
    assert info["layout"]["pages_est"] == 1
    assert info["han_size"] >= 12.0                     # 舒适下限
    assert info["layout"]["margin_mm"][0] <= 18.0       # 自动收窄边距
    assert "target_met" not in info["layout"]           # 达标


def test_target_pages_unreachable_reports():
    """极端长文 + 1 页目标：如实报告未达标（不无限缩字）。"""
    long_text = "\n".join("春江潮水连海平，海上明月共潮生。" for _ in range(60))
    info, _ = make_info({"title": "超长", "text": long_text, "target_pages": 1}, "tp2.html")
    assert info["layout"]["target_met"] is False
    assert info["layout"]["pages_est"] > 1
    assert info["han_size"] >= 10.0                     # 绝对下限


def test_target_pages_respects_user_margin():
    """用户显式设置 margin_mm 时，页数求解不得自动收窄边距。"""
    long_text = "\n".join("春江潮水连海平，海上明月共潮生。" for _ in range(9))
    info, _ = make_info({"title": "春江", "text": long_text,
                         "target_pages": 1, "margin_mm": 18}, "tp3.html")
    assert info["layout"]["margin_mm"] == [18.0, 18.0]


def test_stanza_flow_class_for_oversized_stanza():
    """单节超过一页（连同标题）时标 .flow：允许行边界自然分页。"""
    long_text = "\n".join("春江潮水连海平，海上明月共潮生。" for _ in range(15))
    _, doc = make_info({"title": "长诗", "text": long_text, "couplet": False}, "fl1.html")
    assert 'class="stanza flow"' in doc
    short_info, doc_short = make_info({"title": "静夜思", "text": JYS}, "fl2.html")
    assert 'class="stanza flow"' not in doc_short
    assert doc_short.count('class="stanza">') == 1      # 短诗整节 keep


def test_print_css_protects_header_and_lines():
    """分页保护：标题块/姓名栏原子+黏后文；展示行原子；flow 节允许分页。"""
    css = (ROOT / "templates" / "base.css").read_text(encoding="utf-8")
    assert re.search(r"header\.hd, \.ws-meta, \.grp-head", css)
    assert "break-after: avoid-page" in css and "break-inside: avoid" in css
    assert ".stanza.flow" in css and "break-inside: auto" in css
    assert ".v, .vgrp, .ws-line, .tian-row" in css


def test_worksheet_pairs_tian_row_with_verse():
    """worksheet 诗行：诗句与田字格行包 .vgrp，分页时不分离。"""
    _, doc = make_info({"title": "山行", "template": "worksheet",
                        "text": "远上寒山石径斜，白云生处有人家。"}, "ws1.html")
    grp = re.search(r'<div class="vgrp">.*?</div>\s*</div>', doc, re.S)
    assert grp and 'class="tian-row"' in grp.group(0) and '<div class="v">' in grp.group(0)


def test_new_fields_validation():
    with pytest.raises(rd.RenderError):
        make({"text": JYS, "couplet": "maybe"}, "bad4.html")
    with pytest.raises(rd.RenderError):
        make({"text": JYS, "target_pages": "two"}, "bad5.html")
    with pytest.raises(rd.RenderError):
        make({"text": JYS, "target_pages": 99}, "bad6.html")


def test_layout_info_in_cli_summary():
    r = run_cli("--spec", write_spec(TMP / "cli12.json", {
        "title": "黄鹤楼", "author": "崔颢", "text": LSLV, "target_pages": 1}), "--out", "cli12.html")
    assert r["ok"], r
    assert r["layout"]["strategy"] in ("clause", "couplet")
    assert r["layout"]["pages_est"] == 1
    spec = rd.extract_spec_from_html(TMP / "cli12.html")
    assert spec["target_pages"] == 1                   # 持久进嵌入 spec
    r2 = run_cli("--from-html", "cli12.html", "--set", "couplet=true", "--out", "cli13.html")
    assert r2["ok"] and r2["layout"]["strategy"] == "couplet"


# ---------------------------------------------------------------------------
# 语义折行与几何行组织（v1.3.1）
# ---------------------------------------------------------------------------

GUSHI_HEAD = ("《望洞庭》\n〔唐〕刘禹锡\n湖光秋月两相和，潭面无风镜未磨。\n"
              "遥望洞庭山水翠，白银盘里一青螺。\n\n"
              "《忆江南》\n〔唐〕白居易\n江南好，风景旧曾谙。\n"
              "日出江花红胜火，春来江水绿如蓝。\n能不忆江南？")


def test_wrap_breaks_only_at_clause_boundary():
    """窄栏触发折行时：断点只在句读后——「未磨。」「如蓝。」绝不与所属小句分离。"""
    long_text = GUSHI_HEAD + "\n\n" + "\n\n".join(
        f"《其{i}》\n湖光秋月两相和，潭面无风镜未磨。" for i in range(2, 12))
    _, doc = make_info({"title": "古诗", "text": long_text,
                        "columns": 2, "han_size": 40}, "wb1.html")
    # 字间无断点：任何汉字单元后都不允许 wbr（句读后才是合法断点）
    assert not re.search(r'<span class="h">[\u4e00-\u9fff]</span></ruby><wbr>', doc)
    # 小句完整：「潭面无风镜未磨。」「春来江水绿如蓝。」各自独占完整展示行
    vs = re.findall(r'<div class="v">((?:(?!</div>).)*)</div>', doc, re.S)
    han_lines = [_han_of(v) for v in vs]
    assert "潭面无风镜未磨。" in han_lines
    assert "春来江水绿如蓝。" in han_lines


def test_narrow_column_splits_couplets_into_whole_clauses():
    """双栏窄栏：放不下的七言联自动拆为两个完整小句行（非字间折行）。"""
    _, doc = make_info({"title": "古诗", "text": GUSHI_HEAD,
                        "columns": 2, "han_size": 40}, "wb2.html")
    vs = re.findall(r'<div class="v">(.*?)</div>', doc, re.S)
    han_lines = [_han_of(v) for v in vs]
    assert "湖光秋月两相和，" in han_lines and "潭面无风镜未磨。" in han_lines
    assert "春来江水绿如蓝。" in han_lines and "日出江花红胜火，" in han_lines


def test_char_break_fallback_only_without_punct():
    """无句读超长小句（宽度解低于绝对下限）仍需字间兜底折行。"""
    out = make({"title": "超长", "text": "曲" * 50}, "wb3.html")
    doc = out.read_text(encoding="utf-8")
    assert "wrap-ok" in doc
    assert "</ruby><wbr><ruby" in doc                      # 字间兜底断点生效


def test_display_lines_geometry_and_balance():
    """行组织单测：贪心按预算装行 + 尾行均衡。"""
    def frags_of(text):
        ann = pr.annotate(text)
        return rd._split_verse(ann.lines[0])

    # 预算充足：五言两小句合并一行
    lf = frags_of("床前明月光，疑是地上霜。")
    rows = rd._display_lines(lf, 1.86, 20.0)
    assert len(rows) == 1 and _han_of_cells(rows[0]) == "床前明月光，疑是地上霜。"
    # 预算不足：拆为两个完整小句行（绝不字间拆）
    rows = rd._display_lines(lf, 1.86, 10.0)
    assert len(rows) == 2
    assert _han_of_cells(rows[0]) == "床前明月光，" and _han_of_cells(rows[1]) == "疑是地上霜。"
    # 三字句可 3-4 句同行（预算内贪心，非固定字数）
    lf3 = frags_of("岑夫子，丹丘生，将进酒，杯莫停。")
    rows3 = rd._display_lines(lf3, 1.57, 21.5)
    assert len(rows3) == 1 and _han_of_cells(rows3[0]) == "岑夫子，丹丘生，将进酒，杯莫停。"
    # 尾行均衡：[7,3] 预算中间值 → 拆行后尾行 3 字 <40% 预算，回退 7 字句应无效
    #（前行仅 1 小句无法回退）；[3,3,7] 预算只容两小句时尾行为完整小句
    lf2 = frags_of("五花马，千金裘，呼儿将出换美酒。")
    rows2 = rd._display_lines(lf2, 1.57, 11.0)
    assert all(_han_of_cells(r) for r in rows2)
    assert "".join(_han_of_cells(r) for r in rows2) == "五花马，千金裘，呼儿将出换美酒。"


def _han_of_cells(tokens) -> str:
    return "".join(t.text for t in tokens)
