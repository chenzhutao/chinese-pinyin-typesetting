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
    long_long = "曲" * 40
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
    assert r["ok"], r
    assert r["columns"] == 2
    doc = (TMP / "cli10.html").read_text(encoding="utf-8")
    assert "cols-2" in doc
    assert rd.extract_spec_from_html(TMP / "cli10.html")["columns"] == 2
    r2 = run_cli("--from-html", "cli10.html", "--set", "columns=1", "--out", "cli11.html")
    assert r2["ok"] and r2["columns"] == 1
    body1 = re.search(r'<body class="([^"]*)"', (TMP / "cli11.html").read_text(encoding="utf-8")).group(1)
    assert "cols-2" not in body1
