# -*- coding: utf-8 -*-
"""中文注音引擎：文本 → 逐字拼音标注（供 renderer.py 渲染）。

单一实现，poem / reading / worksheet 三种模板共用同一份注音数据。

能力：
- 基于 pypinyin（随 Skill 内置，scripts/_vendor/pypinyin），按词语上下文注音；
- 内置统编语文教材诗歌读音与常见轻声词修正（curated_phrases.json）；
- 结构助词（地/得）、"长" 等高频多音字的启发式判定（结果进 review 提示）；
- "一/不" 变调（统编教材标变调），可关闭；
- 用户 overrides 精确覆盖：index / line+char / phrase / char 四种定位 + 防误改守卫；
- 拼音输入兼容 cuī / cui1 / lv4 等写法。

不承诺 100% 正确：启发式判定与多音字都会写入 review 列表，由调用方
（Agent）转述给用户确认。
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_VENDOR = _HERE / "_vendor"
if _VENDOR.is_dir() and str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

try:
    from pypinyin import pinyin as _pinyin, Style
    from pypinyin.seg import mmseg
except Exception as _e:  # pragma: no cover - vendored copy ships with the skill
    raise ImportError(f"内置 pypinyin 加载失败（scripts/_vendor/pypinyin）: {_e}") from _e

# 统编教材诗歌读音的"古今/审音分歧"提示（出现在文本中时写入 notes）
with open(_VENDOR / "pypinyin" / "curated_phrases.json", encoding="utf-8") as _fp:
    _CURATED = json.load(_fp)
TEXTBOOK_NOTES = _CURATED.get("__notes__", {})

# 小学阶段真实会两读的高频多音字（出现且确有多个候选读音时列入 review）
COMMON_POLYPHONES = set(
    "阿吧把耙伯泊薄剥曝参差长朝称乘盛重传创大待倒都度恶发仿佛服干杆"
    "给更供骨冠好号喝和荷横华划还晃混几系济加将教解结禁劲卷看"
    "乐累勒率笼露论落脉没闷蒙眯秘模磨难哪能粘宁弄女胖炮喷"
    "铺朴悄强雀曲圈任塞扫丧色煞扇少舍胜省似属数说宿缩遂弹提"
    "条挑贴同统秃吐屯拓外为乌纤鲜相巷肖兴行熊畜旋血咽燕要叶一"
    "遗椅义音应拥佣与宇羽吁圆员约晕载赞脏凿泽扎乍粘涨挣殖只"
    "旨质中种转幢锥缀准着仔滋作坐衰斜骑见当得上地差"
)

_HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_LATIN_RE = re.compile(r"[A-Za-z0-9]+(?:[.\-'][A-Za-z0-9]+)*")
_TONE_MARKS = {1: "āōēīūǖ", 2: "áóéíúǘ", 3: "ǎǒěǐǔǚ", 4: "àòèìùǜ"}
_MARKED = {m: t for t, marks in _TONE_MARKS.items() for m in marks}


class PinyinSpecError(ValueError):
    """输入（spec / overrides / 拼音写法）不合法。"""


# ---------------------------------------------------------------------------
# Token 与标注结果
# ---------------------------------------------------------------------------

@dataclass
class Token:
    kind: str                    # 'han' | 'latin' | 'space' | 'punct'
    text: str
    pinyin: str | None = None    # 带调拼音；轻声无调号
    index: int = 0               # 整段文本中的码点偏移（han token 必为单字）
    word: str = ""               # 分词命中词语（pypinyin 词典），未命中即自身
    overridden: bool = False

    @property
    def is_han(self) -> bool:
        return self.kind == "han"


@dataclass
class Annotation:
    text: str
    lines: list[list[Token]] = field(default_factory=list)
    review: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    applied_overrides: list[dict] = field(default_factory=list)
    missing: list[dict] = field(default_factory=list)

    def han_tokens(self):
        for line in self.lines:
            for t in line:
                if t.is_han:
                    yield t

    @property
    def hanzi_count(self) -> int:
        return sum(1 for _ in self.han_tokens())


def is_han_char(ch: str) -> bool:
    return bool(_HAN_RE.match(ch))


def tone_of(py: str | None) -> int:
    """1-4 声调；5 轻声/无调；0 无拼音。"""
    if not py:
        return 0
    for ch in py:
        if ch in _MARKED:
            return _MARKED[ch]
    return 5


# ---------------------------------------------------------------------------
# 拼音写法归一化
# ---------------------------------------------------------------------------

def numeric_to_mark(syl: str) -> str:
    """cui1 → cuī；lv4 → lǜ；cui → cui；非法写法原样返回（由正则校验兜底）。"""
    syl = syl.strip().lower().replace("v", "ü").replace("u:", "ü")
    m = re.fullmatch(r"([a-zümn]+?)([1-5])", syl)
    if not m:
        return syl
    base, tone = m.group(1), int(m.group(2))
    if tone == 5:
        return base
    marks = _TONE_MARKS[tone]
    # 标调位置：ü 优先；iu/ui 标后者；否则按 a-o-e-i-u 顺序取第一个元音
    if "ü" in base:
        i = base.index("ü")
        return base[:i] + marks[5] + base[i + 1:]
    for pair in ("iu", "ui"):
        if pair in base:
            i = base.index(pair) + 1
            return base[:i] + marks[4 if pair == "iu" else 3] + base[i + 1:]
    for i, v in ((base.find("a"), "a"), (base.find("o"), "o"), (base.find("e"), "e")):
        if i >= 0:
            return base[:i] + marks[{"a": 0, "o": 1, "e": 2}[v]] + base[i + 1:]
    for v in ("i", "u"):
        if v in base:
            i = base.index(v)
            return base[:i] + marks[3 if v == "i" else 4] + base[i + 1:]
    # 剩余：hm/hng 等，用组合变音符
    return unicodedata.normalize("NFC", base + {1: "\u0304", 2: "\u0301", 3: "\u030c", 4: "\u0300"}[tone])


_SYL_CHARS = "a-zü" + "".join(_TONE_MARKS.values()) + "ńňǹḿm̄m̌m̀"
_SYL_RE = re.compile(f"^[{_SYL_CHARS}]+$")


def normalize_pinyin(value, expect: int | None = None) -> list[str]:
    """把用户给的拼音归一化为音节列表；expect 校验音节数。"""
    if not isinstance(value, str) or not value.strip():
        raise PinyinSpecError("pinyin 不能为空")
    syls = []
    for p in re.split(r"[\s,，、;；/]+", value.strip()):
        s = numeric_to_mark(p)
        if not _SYL_RE.match(s):
            raise PinyinSpecError(f"拼音写法无法识别：{p!r}（示例：cuī、cui1、shang4）")
        syls.append(s)
    if expect is not None and len(syls) != expect:
        raise PinyinSpecError(
            f"拼音音节数({len(syls)})与目标汉字数({expect})不一致：{value!r}")
    return syls


def retone(syl: str, tone: int) -> str:
    """把音节改为指定声调（1-4；5=轻声去调号）。"""
    plain = unicodedata.normalize(
        "NFC", "".join(
            (unicodedata.normalize("NFD", ch)[0] if ch in _MARKED else ch)
            for ch in syl))
    return numeric_to_mark(plain + str(tone)) if tone < 5 else plain


# ---------------------------------------------------------------------------
# 基础标注
# ---------------------------------------------------------------------------

def _classify_lines(text: str) -> list[list[Token]]:
    """按行切分并分类；han 每字一个 Token，latin/数字成词，空白保留。"""
    lines: list[list[Token]] = []
    offset = 0
    for raw_line in text.split("\n"):
        toks: list[Token] = []
        i = 0
        while i < len(raw_line):
            ch = raw_line[i]
            if is_han_char(ch):
                toks.append(Token("han", ch, index=offset + i))
                i += 1
            elif ch.isspace():
                j = i
                while j < len(raw_line) and raw_line[j].isspace():
                    j += 1
                toks.append(Token("space", raw_line[i:j], index=offset + i))
                i = j
            else:
                m = _LATIN_RE.match(raw_line, i)
                if m:
                    toks.append(Token("latin", m.group(), index=offset + i))
                    i = m.end()
                else:
                    toks.append(Token("punct", ch, index=offset + i))
                    i += 1
        lines.append(toks)
        offset += len(raw_line) + 1
    return lines


def _annotate_han_runs(lines: list[list[Token]]) -> None:
    """对每行连续汉字串按 pypinyin 词语模式注音（上下文=同行词语）。"""
    for toks in lines:
        i = 0
        while i < len(toks):
            if toks[i].kind != "han":
                i += 1
                continue
            j = i
            while j < len(toks) and toks[j].kind == "han":
                j += 1
            run = "".join(t.text for t in toks[i:j])
            readings = _pinyin(run, style=Style.TONE)
            if len(readings) != len(run):  # 防御：逐字回退
                readings = _pinyin(list(run), style=Style.TONE)
            words = list(mmseg.seg.cut(run))
            wpos, wstart = {}, 0
            for w in words:
                for k in range(len(w)):
                    wpos[wstart + k] = w
                wstart += len(w)
            for k, t in enumerate(toks[i:j]):
                t.pinyin = readings[k][0] if k < len(readings) and readings[k] else None
                t.word = wpos.get(k, t.text)
            i = j


# ---------------------------------------------------------------------------
# 上下文规则：结构助词 / 高频多音字（全部进 review）
# ---------------------------------------------------------------------------

_GROW_NEXT = set("得着出大高成满在到不起过好个来")
_DI_PREV_BLOCK = set("块片亩分垄畦处个这那此当各每某")
_DEGREE_PREV = set("很最太真多好不有点儿稍格外更")


def _context_fixes(lines: list[list[Token]], rule_review: list[dict]) -> None:
    for toks in lines:
        han_idx = [k for k, t in enumerate(toks) if t.is_han]
        for pos, k in enumerate(han_idx):
            t = toks[k]
            prev_h = toks[han_idx[pos - 1]] if pos > 0 else None
            next_h = toks[han_idx[pos + 1]] if pos + 1 < len(han_idx) else None
            standalone = len(t.word) == 1

            if t.text == "地" and standalone:
                if prev_h and next_h and prev_h.text not in _DI_PREV_BLOCK:
                    _rule(t, rule_review, "de", "结构助词「地」")
                else:
                    _ambiguous(t, rule_review, "dì", "「地」名词/助词歧义")
            elif t.text == "得" and standalone:
                if prev_h and next_h:
                    _rule(t, rule_review, "de", "结构助词「得」")
                elif not prev_h and next_h:
                    _ambiguous(t, rule_review, "děi", "句首「得」(děi/de 歧义)")
            elif t.text == "长" and standalone:
                if next_h and next_h.text in _GROW_NEXT:
                    _rule(t, rule_review, "zhǎng", "动词「长」（生长）")
                else:
                    _rule(t, rule_review, "cháng", "形容词「长」（长短）")


def _rule(t: Token, review: list[dict], py: str, reason: str) -> None:
    t.pinyin = py
    review.append({"char": t.text, "pinyin": py, "index": t.index, "kind": "rule", "reason": reason})


def _ambiguous(t: Token, review: list[dict], chosen: str, reason: str) -> None:
    review.append({"char": t.text, "pinyin": chosen, "index": t.index,
                   "kind": "ambiguous", "reason": reason})


# ---------------------------------------------------------------------------
# "一 / 不" 变调（统编教材标变调；sandhi='none' 时全部还原本调）
# ---------------------------------------------------------------------------

_NUM_CHARS = set("零一二三四五六七八九十百千万亿")
_ORDINAL_PREV = set("第初")
_ORDINAL_NEXT = set("年级班月号层等初")


def _tone_sandhi(lines: list[list[Token]]) -> None:
    for toks in lines:
        han_idx = [k for k, t in enumerate(toks) if t.is_han]
        for pos, k in enumerate(han_idx):
            t = toks[k]
            if t.overridden or t.text not in ("一", "不"):
                continue
            next_h = toks[han_idx[pos + 1]] if pos + 1 < len(han_idx) else None
            prev_h = toks[han_idx[pos - 1]] if pos > 0 else None
            if t.text == "一":
                t.pinyin = _yi_tone(prev_h, next_h)
            else:
                t.pinyin = "bú" if next_h and tone_of(next_h.pinyin) == 4 else "bù"


def _yi_tone(prev_h, next_h) -> str:
    if not next_h:
        return "yī"                                   # 句末本调
    if next_h.text in _NUM_CHARS:
        return "yī"                                   # 一二三 / 十一
    if prev_h and (prev_h.text in _NUM_CHARS | _ORDINAL_PREV):
        return "yī"                                   # 第十一、初一
    if next_h.text in _ORDINAL_NEXT:
        return "yī"                                   # 一年级 / 一月
    if prev_h and prev_h.text == next_h.text:
        return "yi"                                   # 看一看（轻读）
    return "yí" if tone_of(next_h.pinyin) == 4 else "yì"


def _restore_base_tone(lines: list[list[Token]]) -> None:
    for toks in lines:
        for t in toks:
            if t.is_han and not t.overridden and t.text in ("一", "不"):
                t.pinyin = "yī" if t.text == "一" else "bù"


# ---------------------------------------------------------------------------
# 用户 overrides（在自动规则之后应用，最终生效）
# ---------------------------------------------------------------------------

def _iter_line_tokens(a: Annotation):
    """产出 (非空行号从1计, 行内汉字序号从1计, token, 行文本)。"""
    line_no = 0
    for toks in a.lines:
        if not any(t.is_han for t in toks):
            continue
        line_no += 1
        han_seen = 0
        for t in toks:
            if t.is_han:
                han_seen += 1
                yield line_no, han_seen, t, "".join(x.text for x in toks)


def _body_text(a: Annotation) -> str:
    return "\n".join("".join(t.text for t in toks) for toks in a.lines)


def _find_phrase_spans(a: Annotation, phrase: str) -> list[list[Token]]:
    hits: list[list[Token]] = []
    for toks in a.lines:
        i = 0
        while i < len(toks):
            window = toks[i:i + len(phrase)]
            if "".join(t.text for t in window) == phrase:
                hits.append(window)
                i += len(phrase)
            else:
                i += 1
    return hits


def _locate(a: Annotation, ov: dict) -> list[tuple[Token, str]]:
    """把一条 override 解析为 [(token, 新拼音), ...]。"""
    has_pos_index = "index" in ov
    has_pos_line = "line" in ov and "char" in ov
    has_phrase = "phrase" in ov
    has_char = "char" in ov and not has_pos_line
    picked = sum(1 for x in (has_pos_index, has_pos_line, has_phrase, has_char) if x)
    if picked != 1:
        raise PinyinSpecError(
            "override 必须且只能用一种定位：index / line+char / phrase / char")
    tone = ov.get("tone")
    if "pinyin" not in ov and tone is None:
        raise PinyinSpecError("override 需要 pinyin 或 tone 字段")
    if "pinyin" in ov and tone is not None:
        raise PinyinSpecError("pinyin 与 tone 二选一，不要同时给")

    targets: list[Token] = []
    per_span = 1            # phrase 定位时每处出现的汉字数（all 模式按此循环分配音节）

    if has_pos_index:
        idx = ov["index"]
        if not isinstance(idx, int) or isinstance(idx, bool) or idx < 0:
            raise PinyinSpecError(f"index 必须是非负整数（0 起始，按整段文本码点计）：{idx!r}")
        targets = [t for t in a.han_tokens() if t.index == idx][:1]
        if not targets:
            near = a.text[max(0, idx - 6):idx + 6].replace("\n", "⏎")
            raise PinyinSpecError(
                f"index={idx} 未命中汉字（该位置前后文本：…{near}…）。"
                "index 按整段 text 的码点偏移计算（含标点与换行，0 起始）")
        guard = ov.get("expect")
        if guard and targets[0].text != guard:
            raise PinyinSpecError(
                f"index={idx} 处汉字是「{targets[0].text}」，与守卫字符 expect=「{guard}」不符")

    elif has_pos_line:
        ln, cn = ov.get("line"), ov.get("char")
        if not (isinstance(ln, int) and not isinstance(ln, bool) and ln >= 1
                and isinstance(cn, int) and not isinstance(cn, bool) and cn >= 1):
            raise PinyinSpecError(
                "line/char 必须是正整数（行=正文非空行从 1 计；字=行内汉字序号从 1 计，不含标点）")
        targets = [t for l, c, t, _ in _iter_line_tokens(a) if l == ln and c == cn][:1]
        if not targets:
            total = max((l for l, *_ in _iter_line_tokens(a)), default=0)
            raise PinyinSpecError(
                f"line={ln}, char={cn} 未命中（正文共 {total} 个非空行；"
                "行号按非空行从 1 计，字序号只数汉字）")

    elif has_phrase:
        phrase = ov["phrase"]
        if not isinstance(phrase, str) or not phrase or not all(is_han_char(c) for c in phrase):
            raise PinyinSpecError(f"phrase 必须是纯汉字串：{phrase!r}")
        spans = _find_phrase_spans(a, phrase)
        if not spans:
            raise PinyinSpecError(f"正文中未找到「{phrase}」")
        per_span = len(spans[0])          # 每处出现的汉字数（= phrase 长度）
        occ = ov.get("occurrence")
        if ov.get("all"):
            targets = [t for span in spans for t in span]
        elif occ is None:
            if len(spans) > 1:
                where = "、".join(sorted({f"第{l}句" for l, _c, t, _ in _iter_line_tokens(a)
                                          if any(t is s[0] for s in spans)}))
                raise PinyinSpecError(
                    f"「{phrase}」出现 {len(spans)} 次（{where}），"
                    f"请加 occurrence（从 1 计）或 \"all\": true 防止误改")
            targets = spans[0]
        elif isinstance(occ, int) and 1 <= occ <= len(spans):
            targets = spans[occ - 1]
        else:
            raise PinyinSpecError(
                f"occurrence={occ!r} 超出「{phrase}」的出现次数 {len(spans)}")

    else:  # 单字 char
        ch = ov["char"]
        if not isinstance(ch, str) or len(ch) != 1 or not is_han_char(ch):
            raise PinyinSpecError(f"char 必须是单个汉字：{ch!r}")
        hits = [t for t in a.han_tokens() if t.text == ch]
        if not hits:
            raise PinyinSpecError(f"正文中没有「{ch}」")
        occ = ov.get("occurrence")
        if ov.get("all"):
            targets = hits
        elif occ is None:
            if len(hits) > 1:
                where = "、".join(f"第{l}句第{c}字" for l, c, t, _ in _iter_line_tokens(a)
                                  if t.text == ch)
                raise PinyinSpecError(
                    f"「{ch}」出现 {len(hits)} 次（{where}）；"
                    f"请加 occurrence（从 1 计）或 \"all\": true 防止误改")
            targets = hits[:1]
        elif isinstance(occ, int) and 1 <= occ <= len(hits):
            targets = [hits[occ - 1]]
        else:
            raise PinyinSpecError(f"occurrence={occ!r} 超出「{ch}」的出现次数 {len(hits)}")

    # char+all：同一读音应用到每个出现位置（音节数=1）；
    # phrase+all：整串拼音按 per_span 逐字循环应用到每一处；
    # 其余定位：逐字一音节。
    out: list[tuple[Token, str]] = []
    if tone is not None:
        if not (isinstance(tone, int) and not isinstance(tone, bool) and 1 <= tone <= 5):
            raise PinyinSpecError("tone 必须是 1-5（5=轻声）")
        for t in targets:
            if not t.pinyin:
                raise PinyinSpecError(
                    f"「{t.text}」（index={t.index}）当前无拼音，不能只改声调，请给完整 pinyin")
            out.append((t, retone(t.pinyin, tone)))
    elif has_char and ov.get("all"):
        syl = normalize_pinyin(ov["pinyin"], expect=1)[0]
        out = [(t, syl) for t in targets]
    elif has_phrase and ov.get("all"):
        syls = normalize_pinyin(ov["pinyin"], expect=per_span)
        out = [(t, syls[k % per_span]) for k, t in enumerate(targets)]
    else:
        out.extend(zip(targets, normalize_pinyin(ov["pinyin"], expect=len(targets))))
    return out


def apply_overrides(a: Annotation, overrides) -> list[dict]:
    """应用用户 overrides；返回实际改动摘要。"""
    applied = []
    for n, ov in enumerate(overrides or []):
        if not isinstance(ov, dict):
            raise PinyinSpecError(f"overrides[{n}] 必须是对象：{ov!r}")
        changes = _locate(a, ov)
        for t, py in changes:
            t.pinyin = py
            t.overridden = True
        applied.append({
            "chars": "".join(t.text for t, _ in changes),
            "pinyin": " ".join(py for _, py in changes),
            "override": ov,
        })
    return applied


# ---------------------------------------------------------------------------
# review / notes
# ---------------------------------------------------------------------------

def _build_review(a: Annotation, rule_review: list[dict]) -> list[dict]:
    out: dict[int, dict] = {}
    for r in rule_review:
        out[r["index"]] = r
    for ln, hn, t, _lt in _iter_line_tokens(a):
        if t.overridden or t.text not in COMMON_POLYPHONES:
            continue
        if t.index in out:
            out[t.index].update(line=ln, char_pos=hn)
            continue
        het = _pinyin(t.text, style=Style.TONE, heteronym=True)
        alts = sorted({s[0] for s in het[0]}) if het and het[0] else []
        if len(alts) < 2:          # 无真实二读（如 音/坐）不打扰用户
            continue
        out[t.index] = {
            "char": t.text, "pinyin": t.pinyin, "index": t.index,
            "line": ln, "char_pos": hn, "kind": "polyphone",
            "reason": "多音字", "alternatives": alts,
        }
    return [out[k] for k in sorted(out)]


def _build_notes(a: Annotation) -> list[str]:
    body = _body_text(a)
    return [msg for phrase, msg in TEXTBOOK_NOTES.items() if phrase in body]


# ---------------------------------------------------------------------------
# 对外主入口
# ---------------------------------------------------------------------------

def annotate(text: str, overrides=None, sandhi: str = "yi_bu") -> Annotation:
    """正文 → Annotation（逐字拼音 + review/notes/applied_overrides）。"""
    if not isinstance(text, str) or not text.strip():
        raise PinyinSpecError("text 不能为空")
    if sandhi not in ("yi_bu", "none"):
        raise PinyinSpecError("sandhi 只支持 yi_bu / none")

    a = Annotation(text=text)
    a.lines = _classify_lines(text)
    _annotate_han_runs(a.lines)

    rule_review: list[dict] = []
    _context_fixes(a.lines, rule_review)
    if sandhi == "yi_bu":
        _tone_sandhi(a.lines)
    else:
        _restore_base_tone(a.lines)

    a.applied_overrides = apply_overrides(a, overrides)
    a.review = _build_review(a, rule_review)
    a.notes = _build_notes(a)
    a.missing = [{"char": t.text, "index": t.index}
                 for t in a.han_tokens() if t.pinyin is None]
    return a
