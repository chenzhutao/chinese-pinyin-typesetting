# spec 字段参考（generate.py）

所有字段除 `text` 外均可省略。命令行等价缩写：`--set key=value` 可改任意字段
（value 按 JSON 解析，失败则按字符串）、`--override '<JSON>'` 追加一条 overrides、
`--from-html <file>` 从既有产物恢复 spec 后再改。

## 内容

| 字段 | 类型/默认 | 说明 |
|---|---|---|
| `text` | string（必填） | 正文。`\n` 换行；**空行分段**（诗联/课文段落） |
| `title` | string | 标题；显示时自动去《》。有汉字且 `annotate_title` 时逐字注音 |
| `author` | string | 作者，如"李白" |
| `dynasty` | string | 朝代，如"唐"；显示为"〔唐〕李白" |

## 模板与模式

| 字段 | 合法值 | 默认 | 说明 |
|---|---|---|---|
| `template` | auto/poem/reading/worksheet | auto | auto：行短(≤20 单元)且≥1 行 → poem，否则 reading |
| `mode` | both/hanzi/pinyin/blank_pinyin | both | 对所有模板通用；见 SKILL.md |
| `copy_rows` | 0-3 | worksheet=1，其余 0 | 每句下方的田字格书写行数 |
| `annotate_title` | bool | true | 标题是否注音 |
| `annotate_author` | bool | false | 作者行是否注音 |

## 版面

| 字段 | 合法值 | 默认 | 说明 |
|---|---|---|---|
| `han_size` | 8-120 | poem 32 / reading 15.5 / worksheet 24 | 汉字字号 pt；超页宽/页高时自动缩小 |
| `pinyin_ratio` | 0.25-0.8 | 0.42 | 拼音字号 = 汉字 × 比例（`pinyin_size` 可直接给 pt 覆盖） |
| `page` | A4/A5/LETTER | A4 | 纸张 |
| `landscape` | bool | false | 横向 |
| `margin_mm` | 数值或 [上下,左右] | 18 | 页边距 mm |
| `font` | kai/song/hei | kai | 汉字字体（楷体最接近教材） |
| `line_gap_scale` | ≥0.2 | 1.0 | 行距缩放 |
| `footer` | string | "" | 页脚小字（如"请家长签字：____"） |

## 注音

| 字段 | 合法值 | 默认 | 说明 |
|---|---|---|---|
| `tone_sandhi` | yi_bu/none | yi_bu | "一/不"是否按统编教材标变调（none=全部本调） |
| `overrides` | array | [] | 读音覆盖，见下 |

### overrides 四种定位（每条必须且只能用一种）

```json
{"index": 6,  "pinyin": "cuī", "expect": "衰"}     // 整段文本码点偏移，0 起始，含标点换行
{"line": 3,  "char": 2, "tone": 4}                  // 第 3 个非空行第 2 个汉字；tone 只改声调
{"phrase": "鬓毛衰", "pinyin": "bìn máo cuī", "occurrence": 1}   // 或 "all": true
{"char": "衰", "pinyin": "cuī", "occurrence": 1}    // 或 "all": true（同一读音应用到每处）
```

- `pinyin` 与 `tone`（1-5，5=轻声）二选一；拼音兼容 `cuī`/`cui1`/`lv4`/`shang4`。
- `expect`（index 定位）守卫：位置上的汉字与预期不符时报错，防错位误改。
- 同一目标多处出现且未指定 `occurrence`/`all` 时报错并列出全部位置。

## 命令行

```
generate.py --spec <spec.json> [--out <file.html>] [--pdf]
generate.py --from-html <prev.html> [--set k=v ...] [--override <json> ...] [--out ...] [--pdf]
generate.py --text-file <plain.txt>   # 自动识别《标题》与作者行（含"[唐] 李白"）
generate.py --text "《静夜思》李白\n床前明月光，…" [--title ...] [--author ...]
```

退出码：0 成功；2 输入错误（stdout JSON `ok:false, error`）。
`--pdf` 需要执行环境中装有 Chrome/Chromium/Edge（通过 PATH 或常见安装位置查找）；
找不到浏览器时返回 `pdf.ok=false` 并说明原因，HTML 本身可在任何浏览器打印为 PDF。

## 输出摘要字段（stdout JSON）

`ok` `output` `template` `mode` `hanzi_count` `han_size_pt` `pinyin_size_pt`
`overrides_applied[]`（chars/pinyin/override）`review[]`（char/pinyin/line/char_pos/
kind=rule|polyphone|ambiguous/reason/alternatives）`notes[]`（教材读音分歧提示）
`warnings[]`（生僻字无拼音、超长句折行）`spec_echo`。

review/notes 必须转述给用户；用户回应后用 overrides + `--from-html` 迭代。
