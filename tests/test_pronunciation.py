# -*- coding: utf-8 -*-
"""注音引擎单元测试：汉字-拼音数量/位置、声调符号、多音字、
教材读音、overrides 定位与守卫、一/不 变调、轻声、原文不污染。"""

import sys
import json
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pronunciation as pr  # noqa: E402

JYS = "床前明月光，\n疑是地上霜。\n举头望明月，\n低头思故乡。"
HUIXIANG = ("少小离家老大回，\n乡音无改鬓毛衰。\n"
            "儿童相见不相识，\n笑问客从何处来。")
SHANXING = ("远上寒山石径斜，\n白云生处有人家。\n"
            "停车坐爱枫林晚，\n霜叶红于二月花。")
WULUSHAN = ("日照香炉生紫烟，遥看瀑布挂前川。\n"
            "飞流直下三千尺，疑是银河落九天。")
DUANWEN = ("小朋友们高高兴兴地去上学了。\n"
           "他长得很高，头发很长。\n"
           "2024年10月1日，我们在教室里读 Aa Bb，唱《小星星》。\n"
           "看一看，一行白鹭上青天！")


def py_of(a):
    return {(t.index, t.text): t.pinyin for t in a.han_tokens()}


def han_at(a, line_no, char_no):
    for ln, cn, t, _ in pr._iter_line_tokens(a):
        if ln == line_no and cn == char_no:
            return t
    raise AssertionError(f"no han at line {line_no} char {char_no}")


# ---- 数量与位置 ----------------------------------------------------------

@pytest.mark.parametrize("text", [JYS, HUIXIANG, SHANXING, WULUSHAN, DUANWEN])
def test_hanzi_count_matches(text):
    a = pr.annotate(text)
    expect = sum(1 for c in text if pr.is_han_char(c))
    assert a.hanzi_count == expect
    assert all(t.pinyin for t in a.han_tokens()), "每个汉字都应有拼音"


def test_original_text_not_polluted():
    for text in (JYS, DUANWEN, HUIXIANG):
        a = pr.annotate(text, overrides=[{"index": 0, "tone": 4}])
        assert a.text == text
        assert "".join(t.text for t in a.han_tokens()) == \
            "".join(c for c in text if pr.is_han_char(c))


def test_tone_marks_and_specials():
    a = pr.annotate("绿女出门旅游，女儿的皮肤绿绿的。")
    pys = [t.pinyin for t in a.han_tokens()]
    assert "lǜ" in pys and "nǚ" in pys          # ü 声调正确
    a = pr.annotate("妈妈看着弟弟。")
    pys = [t.pinyin for t in a.han_tokens()]
    assert pys[1] == "ma" and pys[-1] == "di"   # 轻声无调号
    a = pr.annotate("春眠不觉晓，处处闻啼鸟。")
    marks = set("āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ")
    assert any(ch in marks for t in a.han_tokens() for ch in (t.pinyin or ""))


def test_latin_digits_punct_preserved():
    a = pr.annotate(DUANWEN)
    line3 = a.lines[2]
    kinds = [(t.kind, t.text) for t in line3]
    assert ("latin", "2024") in kinds and ("latin", "Aa") in kinds
    assert any(t.text == "《" for t in line3)
    assert pr.annotate("hello 世界 123").lines[0][0].text == "hello"


# ---- 教材读音 / 多音字 ----------------------------------------------------

def test_textbook_poem_readings():
    a = pr.annotate("风吹草低见牛羊")
    assert han_at(a, 1, 5).pinyin == "xiàn"
    a = pr.annotate("千里江陵一日还")
    assert han_at(a, 1, 7).pinyin == "huán"
    a = pr.annotate("朝辞白帝彩云间")
    assert han_at(a, 1, 1).pinyin == "zhāo"
    a = pr.annotate("白发三千丈")
    assert han_at(a, 1, 2).pinyin == "fà"


def test_shuail_declared_and_overridable():
    a = pr.annotate(HUIXIANG)
    assert han_at(a, 2, 7).pinyin == "shuāi"            # 统编教材默认
    assert any("cuī" in n for n in a.notes)             # 提示旧读分歧
    a2 = pr.annotate(HUIXIANG, overrides=[{"phrase": "鬓毛衰", "pinyin": "bìn máo cuī"}])
    assert han_at(a2, 2, 7).pinyin == "cuī"


def test_context_polyphones():
    a = pr.annotate("他长得很高，头发很长。")
    assert han_at(a, 1, 2).pinyin == "zhǎng"
    assert han_at(a, 1, 9).pinyin == "cháng"
    a = pr.annotate("小朋友们高高兴兴地去上学了。")
    assert han_at(a, 1, 9).pinyin == "de"              # 结构助词
    a = pr.annotate("认真地上课。")
    assert han_at(a, 1, 3).pinyin == "dì"               # 名词义（词典词"地上"）


def test_yi_bu_sandhi():
    a = pr.annotate("一行白鹭上青天")
    assert han_at(a, 1, 1).pinyin == "yì"
    a = pr.annotate("不是")
    assert han_at(a, 1, 1).pinyin == "bú"
    a = pr.annotate("看一看")
    assert han_at(a, 1, 2).pinyin == "yi"
    a = pr.annotate("一，二，三")                        # 数数：本调
    assert han_at(a, 1, 1).pinyin == "yī"
    a = pr.annotate("一不是二", sandhi="none")           # 关闭变调 → 本调
    assert han_at(a, 1, 1).pinyin == "yī" and han_at(a, 1, 2).pinyin == "bù"


# ---- overrides 定位与守卫 -------------------------------------------------

def test_override_by_index_user_example():
    a = pr.annotate("乡音无改鬓毛衰", overrides=[{"index": 6, "pinyin": "cuī"}])
    assert [t.pinyin for t in a.han_tokens()] == \
        ["xiāng", "yīn", "wú", "gǎi", "bìn", "máo", "cuī"]


def test_override_by_line_char_and_tone():
    a = pr.annotate(JYS, overrides=[{"line": 3, "char": 2, "tone": 4}])
    assert han_at(a, 3, 2).pinyin == "tòu"              # 头 tóu → 四声
    assert han_at(a, 3, 2).overridden


def test_override_numeric_pinyin_and_lv():
    a = pr.annotate("绿叶", overrides=[{"char": "绿", "pinyin": "lv4"}])
    assert [t.pinyin for t in a.han_tokens()] == ["lǜ", "yè"]


def test_override_guards_against_wrong_target():
    with pytest.raises(pr.PinyinSpecError, match="守卫"):
        pr.annotate("乡音无改鬓毛衰", overrides=[{"index": 6, "expect": "斜", "pinyin": "cuī"}])
    with pytest.raises(pr.PinyinSpecError, match="未命中"):
        pr.annotate(JYS, overrides=[{"index": 99, "pinyin": "cuī"}])
    with pytest.raises(pr.PinyinSpecError, match="出现 2 次"):
        pr.annotate("举头望明月，低头思故乡。", overrides=[{"char": "头", "pinyin": "tóu"}])
    with pytest.raises(pr.PinyinSpecError, match="音节数"):
        pr.annotate("鬓毛衰", overrides=[{"phrase": "鬓毛衰", "pinyin": "cuī"}])
    with pytest.raises(pr.PinyinSpecError, match="二选一"):
        pr.annotate("衰", overrides=[{"char": "衰", "pinyin": "cuī", "tone": 1}])


def test_override_occurrence_disambiguation():
    a = pr.annotate("举头望明月，低头思故乡。",
                    overrides=[{"char": "头", "occurrence": 2, "tone": 2}])
    heads = [t for t in a.han_tokens() if t.text == "头"]
    assert heads[0].pinyin == "tóu" and not heads[0].overridden
    assert heads[1].pinyin == "tóu" and heads[1].overridden


def test_override_phrase_all_multisyllable():
    """回归：phrase+all 曾因 len(Token) 崩溃（TypeError，exit 1）。
    逐处整串应用 + 音节数校验仍有效。"""
    a = pr.annotate("厌恶黑夜，也厌恶寒冷。",
                    overrides=[{"phrase": "厌恶", "pinyin": "yàn wù", "all": True}])
    pairs = [(t.text, t.pinyin, t.overridden)
             for t in a.han_tokens() if t.text in "厌恶"]
    assert pairs == [("厌", "yàn", True), ("恶", "wù", True),
                     ("厌", "yàn", True), ("恶", "wù", True)]
    # 三音节短语 × 多处：per_span 循环分配
    a = pr.annotate("博物馆很大，博物馆关门了。",
                    overrides=[{"phrase": "博物馆", "pinyin": "bó wù guǎn", "all": True}])
    seq = [(t.text, t.pinyin) for t in a.han_tokens() if t.text in "博物馆"]
    assert seq == [("博", "bó"), ("物", "wù"), ("馆", "guǎn")] * 2
    # 音节数与短语长度不符 → 规范错误（而非崩溃）
    with pytest.raises(pr.PinyinSpecError, match="音节数"):
        pr.annotate("厌恶黑夜。", overrides=[{"phrase": "厌恶", "pinyin": "yàn", "all": True}])


def test_override_phrase_single_and_occurrence():
    a = pr.annotate("我厌恶冬天。", overrides=[{"phrase": "厌恶", "pinyin": "yàn wù"}])
    assert [t.pinyin for t in a.han_tokens()] == ["wǒ", "yàn", "wù", "dōng", "tiān"]
    a = pr.annotate("厌恶黑夜，也厌恶寒冷。",
                    overrides=[{"phrase": "厌恶", "pinyin": "yàn wù", "occurrence": 2}])
    ys = [t for t in a.han_tokens() if t.text == "厌"]
    assert ys[0].overridden is False and ys[1].overridden is True


def test_override_all_and_phrase_occurrence():
    a = pr.annotate("明月几时有，明月照我还。",
                    overrides=[{"char": "月", "all": True, "pinyin": "yuè"}])
    moons = [t for t in a.han_tokens() if t.text == "月"]
    assert all(m.overridden for m in moons)
    a = pr.annotate("明月出天山，明月几时有。",
                    overrides=[{"phrase": "明月", "occurrence": 2, "pinyin": "míng yuè"}])
    first = [t for t in a.han_tokens()][:2]
    assert not any(t.overridden for t in first)


def test_override_wins_over_sandhi():
    a = pr.annotate("一行白鹭上青天",
                    overrides=[{"char": "一", "pinyin": "yī"}])
    assert han_at(a, 1, 1).pinyin == "yī"

def test_override_priority_over_dictionary_and_context_rules():
    # 词典读音 dé 被用户指定的轻声覆盖；结构助词规则也不能反向覆盖。
    a = pr.annotate("赋得古原草送别",
                    overrides=[{"char": "得", "pinyin": "de"}])
    token = next(t for t in a.han_tokens() if t.text == "得")
    assert token.pinyin == "de" and token.overridden
    assert not any(r["index"] == token.index for r in a.review)

    # 上下文规则将「长」判为 zhǎng，人工指定 cháng 后应以人工结果为准。
    a = pr.annotate("他长得很高。",
                    overrides=[{"char": "长", "pinyin": "cháng"}])
    token = next(t for t in a.han_tokens() if t.text == "长")
    assert token.pinyin == "cháng" and token.overridden
    assert not any(r["index"] == token.index for r in a.review)


def test_override_priority_over_yi_bu_sandhi_and_restore():
    # 覆盖在变调处理之后应用；一、不均应保留人工指定读音。
    a = pr.annotate("一行白鹭上青天，不是",
                    overrides=[
                        {"char": "一", "pinyin": "yī"},
                        {"char": "不", "pinyin": "bù"},
                    ])
    tokens = list(a.han_tokens())
    yi = next(t for t in tokens if t.text == "一")
    bu = next(t for t in tokens if t.text == "不")
    assert yi.pinyin == "yī" and yi.overridden
    assert bu.pinyin == "bù" and bu.overridden


def test_override_phrase_priority_and_order():
    # phrase 覆盖多音词整段；若同一位置出现多条 override，后者按顺序最终生效。
    a = pr.annotate("赋得古原草送别",
                    overrides=[
                        {"phrase": "赋得", "pinyin": "fù dé"},
                        {"char": "得", "pinyin": "de"},
                    ])
    got = [(t.text, t.pinyin, t.overridden) for t in a.han_tokens()[:2]]
    assert got == [("赋", "fù", True), ("得", "de", True)]


# ---- review / notes / 拼音写法 -------------------------------------------

def test_review_lists_polyphones_and_rules():
    a = pr.annotate("他长得很高。")
    chars = {r["char"] for r in a.review}
    assert "长" in chars and "得" in chars
    a = pr.annotate(JYS)
    assert a.review == [] or all(r["kind"] in ("polyphone", "rule", "ambiguous")
                                 for r in a.review)


def test_notes_for_contested_readings():
    assert pr.annotate(HUIXIANG).notes
    assert pr.annotate(SHANXING).notes
    assert not pr.annotate(JYS).notes


def test_numeric_to_mark():
    assert pr.numeric_to_mark("cui1") == "cuī"
    assert pr.numeric_to_mark("shang4") == "shàng"
    assert pr.numeric_to_mark("lv4") == "lǜ"
    assert pr.numeric_to_mark("niu2") == "niú"
    assert pr.numeric_to_mark("hui4") == "huì"
    assert pr.numeric_to_mark("de5") == "de"
    assert pr.retone("tóu", 4) == "tòu"
    assert pr.retone("shuāi", 1) == "shuāi"
    assert pr.retone("yí", 1) == "yī"


def test_error_messages_are_actionable():
    with pytest.raises(pr.PinyinSpecError):
        pr.annotate("")
    with pytest.raises(pr.PinyinSpecError, match="无法识别"):
        pr.normalize_pinyin("cu-i")


def test_repeatable():
    """同一输入重复标注结果一致（无隐藏全局状态）。"""
    first = [(t.text, t.pinyin) for t in pr.annotate(DUANWEN).han_tokens()]
    second = [(t.text, t.pinyin) for t in pr.annotate(DUANWEN).han_tokens()]
    assert first == second


# ---------------------------------------------------------------------------
# 教材词典与守卫（v1.3.2）
# ---------------------------------------------------------------------------

def test_textbook_word_dictionary():
    """词语级词典条目：游子/西子（名词性"子"读 zǐ，非轻声）、赋得（dé）。
    词典命中后不得再被结构助词启发式误改。"""
    a = pr.annotate("慈母手中线，游子身上衣。")
    zi = [t.pinyin for t in a.han_tokens() if t.text == "子"]
    assert zi == ["zǐ"]
    a2 = pr.annotate("欲把西湖比西子。")
    assert [t.pinyin for t in a2.han_tokens() if t.text == "子"] == ["zǐ"]
    a3 = pr.annotate("赋得古原草送别")
    de = [t.pinyin for t in a3.han_tokens() if t.text == "得"]
    assert de == ["dé"]
    # 结构助词规则不受词典影响
    a4 = pr.annotate("他跑得很快。")
    assert [t.pinyin for t in a4.han_tokens() if t.text == "得"] == ["de"]


def test_line_char_override_expect_guard():
    """line+char 定位支持 expect 守卫：位置上的汉字与预期不符时报错，
    防止原文修改后序号错位、拼音标到别的字上。"""
    a = pr.annotate("床前明月光，疑是地上霜。",
                    overrides=[{"line": 1, "char": 1, "tone": 2, "expect": "床"}])
    assert a.lines[0][0].pinyin == "chuáng"
    with pytest.raises(pr.PinyinSpecError, match="守卫字符"):
        pr.annotate("床前明月光，疑是地上霜。",
                    overrides=[{"line": 1, "char": 1, "tone": 2, "expect": "光"}])


def test_review_alternatives_full_syllables():
    """review 的 alternatives 必须是完整音节（曾因取首字符显示 ['b','p']）。"""
    a = pr.annotate("欲把西湖比西子。")
    alts = [r.get("alternatives") for r in a.review if r["char"] == "把"]
    assert alts and all(len(s) >= 2 for s in alts[0])


# ---------------------------------------------------------------------------
# 教材与古诗读音样本库：数据与测试逻辑分离
# ---------------------------------------------------------------------------

READING_DATA_PATH = Path(__file__).resolve().parent / "data" / "pronunciation_readings.json"


def load_reading_cases():
    data = json.loads(READING_DATA_PATH.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    cases = data["cases"]
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids)), "读音样本 id 必须唯一"
    for case in cases:
        assert case["category"] in ("古诗", "教材", "日常语境")
        assert isinstance(case["text"], str) and case["text"]
        assert isinstance(case["target"], str) and len(case["target"]) == 1
        assert isinstance(case["occurrence"], int) and case["occurrence"] >= 1
        assert case["text"].count(case["target"]) >= case["occurrence"]
        assert isinstance(case["pinyin"], str) and case["pinyin"]
    return cases


@pytest.mark.parametrize("case", load_reading_cases(), ids=lambda c: c["id"])
def test_verified_reading_regression(case):
    """逐字按出现次数定位，避免相同汉字重复出现时误判。"""
    tokens = [t for t in pr.annotate(case["text"]).han_tokens()
              if t.text == case["target"]]
    actual = tokens[case["occurrence"] - 1].pinyin
    assert actual == case["pinyin"], (
        f'{case["id"]}: {case["target"]} 第 {case["occurrence"]} 次'
        f'应读 {case["pinyin"]}，实际为 {actual}'
    )
