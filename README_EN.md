# chinese-pinyin-typesetting · Simplified Chinese Hanyu Pinyin Typesetting Skill

[简体中文](README.md) | English

**AI Agent Skill · v1.1.4 · For agents that support Skill loading and local script execution · Zero third-party dependencies · MIT**

An AI Agent Skill that turns classical poems, nursery rhymes, textbook passages, and short essays into **textbook-quality annotated HTML**—each character carries its tone-marked Hanyu Pinyin directly above it (ā á ǎ à, ü, neutral tone), verse lines are centered on a shared baseline, A4 printing never truncates, and pages reflow on phones without horizontal scrolling. The romanization system is Hanyu Pinyin (汉语拼音), the standard for Simplified Chinese in mainland China—**not** Zhuyin / Bopomofo (ㄅㄆㄇ), the phonetic script used in Taiwan, which is not supported.

It is **cross-agent by design**: the [SKILL.md](SKILL.md) in the directory is the usage contract agents read, a CLI is the single execution entry point, and nothing depends on a specific agent's SDK, API, or external services—any agent that supports Skill loading and can run Python ≥3.10 scripts locally (e.g. Claude Code, ZCode) can use it; humans can run it in a terminal too.

## Key Features

- **Per-character annotation**: pinyin sits directly above each character, disambiguated by word context, with full tone marks
- **Built-in textbook readings**: approved readings from China's unified-edition textbooks applied automatically (e.g. 石径斜 *xié*, 一日还 *huán*); 一 / 不 tone sandhi follows textbook convention and can be disabled
- **Review list + optional corrections**: questionable readings go into a `review` list for the agent to relay to the user; the optional `overrides` mechanism supports four locator styles—index, line + character, phrase, single character
- **3 templates × 4 modes**: poem / reading / worksheet × annotated / hanzi-only / pinyin-only / tone-marking practice
- **Iterative regeneration**: `--from-html` recovers all settings and correction history from an existing HTML file; change one parameter, get a new version
- **Self-contained HTML output**: single file, inline CSS, adapts to phones, Ctrl+P prints to A4, optional `--pdf` export via a local Chrome/Edge

## Examples

The `examples/` directory ships 10 genuine outputs (specs embedded, reproducible). GitHub shows HTML as source—clone or download the repo and open them in a browser to see the actual typography:

| Example | Content | Template / mode |
|---|---|---|
| [1_jingyesi_poem.html](examples/1_jingyesi_poem.html) | 《静夜思》 classical poem | poem / both |
| [2_chunxiao_poem.html](examples/2_chunxiao_poem.html) | 《春晓》 classical poem | poem / both |
| [3_wanglushan_poem.html](examples/3_wanglushan_poem.html) | 《望庐山瀑布》 classical poem | poem / both |
| [4_huixiang_cuui.html](examples/4_huixiang_cuui.html) | 《回乡偶书》, 衰 corrected to the traditional reading *cuī* | poem / both + override |
| [5_shanxing_worksheet.html](examples/5_shanxing_worksheet.html) | 《山行》 write-characters-from-pinyin | worksheet / pinyin |
| [6_duanwen_reading.html](examples/6_duanwen_reading.html) | 《秋天的雨（节选）》 textbook passage | reading / both |
| [7_huixiang_hanzi.html](examples/7_huixiang_hanzi.html) | 《回乡偶书》 pinyin-free recitation copy | poem / hanzi |
| [8_chunxiao_blankpy.html](examples/8_chunxiao_blankpy.html) | 《春晓》 tone-marking practice | worksheet / blank_pinyin |
| [9_jingyesi_wshanzi.html](examples/9_jingyesi_wshanzi.html) | 《静夜思》 tianzige handwriting practice | worksheet / hanzi |
| [10_woiuiqing_reading.html](examples/10_woiuiqing_reading.html) | 《我对爱情的理解》 modern short essay | reading / both |

## Installation

Python ≥3.10 is all you need—the pinyin engine is vendored under `scripts/_vendor/` (no pip install, no network access at runtime):

```bash
git clone https://github.com/chenzhutao/chinese-pinyin-typesetting.git
# Or download and unzip the Release ZIP:
# https://github.com/chenzhutao/chinese-pinyin-typesetting/releases/tag/v1.1.4
```

- **For an AI Agent**: place the whole directory into the agent's skills directory (path per your agent's docs, e.g. `~/.claude/skills/`)
- **As a CLI tool**: keep it anywhere and run the commands below
- `--pdf` requires a locally installed Chrome / Chromium / Edge; on Windows, use `python -X utf8 ...` if the console raises encoding errors

## Quick Start

```bash
python scripts/generate.py --text "《静夜思》
李白
床前明月光，疑是地上霜。
举头望明月，低头思故乡。" --out 静夜思.html

# Produce another variant (e.g. a hanzi-only recitation copy)
python scripts/generate.py --from-html 静夜思.html --set mode=hanzi --out 静夜思（背诵版）.html
```

stdout is a JSON summary (including the `review` list of polyphonic flags); exit codes are 0/2. Content can also come from `--text-file` or `--spec`. **Full CLI arguments, the spec field reference, and override syntax: [SKILL.md](SKILL.md) and [references/spec.md](references/spec.md).**

## Templates & Display Modes

| Template | Use |
|---|---|
| `poem` | Classical verse: one centered clause per line, title/dynasty/author separate, font size adapts to 5- or 7-character lines |
| `reading` | Textbook passage: paragraphs preserved, automatic wrapping, mixed Chinese/Latin/digit text |
| `worksheet` | Dictation practice: name/date/score header + tianzige (田字格) writing grids |

Display modes (available for every template): `both` annotated (default) · `hanzi` characters only (recitation) · `pinyin` pinyin only (write characters from pinyin) · `blank_pinyin` tone-marking practice. Layout parameters—font size, paper, font family, margins—are covered in [references/spec.md](references/spec.md).

## Pronunciation Corrections

Automatic annotation is not guaranteed perfect: questionable readings go into `review`, textbook-vs-traditional conflicts into `notes` (e.g. "衰: textbook *shuāi*, traditional *cuī*"), relayed to the user in one sentence by the agent. The default output is usable as-is; `overrides` (an optional mechanism—syntax for the four locator styles in [references/spec.md](references/spec.md)) comes into play only when the user wants a reading changed, and correction history survives `--from-html` iteration. Rare characters, uncommon names, and historical-pronunciation disputes warrant a human check.

## Version

Current: **v1.1.4** (2026-11-14) · MIT (declared in [SKILL.md](SKILL.md)) · Downloads: [Release v1.1.4](https://github.com/chenzhutao/chinese-pinyin-typesetting/releases/tag/v1.1.4)

- v1.1.4: default pinyin size raised to 0.55 of the character size
- v1.1.3: fixed a crash with the phrase + all override locator; first public release

The repository ships 43 unit tests and a 30-check browser audit (`tests/`).
