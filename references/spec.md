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
| `han_size` | 8-120 | poem 32 / reading 15.5 / worksheet 24 | 汉字字号 pt（上限）；实际按版面自动缩小，下限见"自适应排版决策" |
| `pinyin_ratio` | 0.25-0.8 | 0.55 | 拼音字号 = 汉字 × 比例（`pinyin_size` 可直接给 pt 覆盖） |
| `page` | A4/A5/LETTER | A4 | 纸张 |
| `landscape` | bool | false | 横向 |
| `columns` | 1/2 | 1 | 正文栏数；2=双栏（页眉页脚通栏、节不跨栏、窄屏自动回退单栏、打印保持双栏） |
| `couplet` | auto/true/false | auto | 诗行合并策略：auto=按结构自动（短诗一句一行舒展、长诗/横版一联一行紧凑）；true=强制一联一行；false=一句一行。只作用于诗行排版 |
| `target_pages` | 1-50 | 省略 | 页数目标：自动联合调整行合并、字号、行距、页边距，尽量排进目标页数（下限见下） |
| `margin_mm` | 数值或 [上下,左右] | 18 | 页边距 mm；显式指定后 `target_pages` 不再自动收窄边距 |
| `font` | kai/song/hei | kai | 汉字字体（楷体最接近教材） |
| `line_gap_scale` | ≥0.2 | 1.0 | 行距缩放；显式指定后 `target_pages` 不再自动收紧行距 |
| `footer` | string | "" | 页脚小字（如"请家长签字：____"） |

## 自适应排版决策（诗行排版：poem / 诗行 worksheet）

排版层级：**源行**（原文一行）—**小句**（句读处拆分）—**展示行**（实际一行）。两种策略：

- **一句一行（clause，舒展）**：每小句独占一行，绝句/律诗竖版的教材风；
- **一联一行（couplet，紧凑）**：同一源行内的小句按宽度预算合并（约两个七言小句），
  三字句等短句可 3-4 句同行；**绝不跨源行、绝不拆小句**，原文顺序与拼音对应不变。

`couplet=auto` 的选择规则（以最终字号更大、更易读为先）：

- 无 `target_pages`：单页放得下且字号不触底时，取字号更大的策略（绝句/律诗竖版
  通常一句一行 25-32pt；长诗、横版、双栏宽度受限时自动联行）；都不触底则取
  纵向更优者，超出部分在展示行边界自然分页。字号下限 = max(`han_size`×0.55, 10pt)。
- 有 `target_pages`：在（策略 × 边距档 × 行距档）组合中选达到页数目标且字号最大的
  方案。期望字号下限 = max(`han_size`×0.45, 12pt)；达不到时允许降到绝对下限 10pt
  并自动收窄页边距（至低 12mm）与行距（至低 0.3），**不无限缩字**。仍达不到时
  取页数最少的方案并在 `warnings` 如实报告（`layout.target_met=false`）。

分页规则：标题块（标题+作者）与姓名栏原子且黏住后文，**标题绝不孤立成页**；
每个展示行（一联）不拆行；节能整页放下时保持完整，超高节在展示行边界自然分页。
长短句长诗（如《将进酒》）行较长，自动判定可能走 reading 模板，需要居中诗行
版式时显式指定 `"template": "poem"`。

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
`layout`（`strategy`=clause/couplet/flow、`pages_est` 估算页数、`target_pages`、
`margin_mm`、`line_gap_scale`、未达标时 `target_met:false`）
`overrides_applied[]`（chars/pinyin/override）`review[]`（char/pinyin/line/char_pos/
kind=rule|polyphone|ambiguous/reason/alternatives）`notes[]`（教材读音分歧提示）
`warnings[]`（生僻字无拼音、超长句折行、自动联行提示、页数目标未达标）
`spec_echo`。

review/notes 必须转述给用户；用户回应后用 overrides + `--from-html` 迭代。
