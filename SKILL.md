---
name: chinese-pinyin-typesetting
description: 中文拼音注音排版。给古诗、儿歌、课文、短文生成适合小学生阅读、朗诵、背诵和 A4 打印的注音 HTML 文档（汉字上方逐字标注带声调拼音，教材风格排版）。用户提到加拼音、注音、拼音排版、拼音文档、默写练习、看拼音写汉字、注音版/背诵版/朗读版古诗等时使用。支持多音字教材读音与用户校正（如"鬓毛衰"读 cuī）、三种模板（古诗背诵版/课文阅读版/默写练习版）、只显汉字/只显拼音等模式、可选本机 Chrome/Edge 导出 PDF。
license: MIT
metadata:
  version: "1.1.4"
  category: education
  runtime: "Python >= 3.10（仅标准库 + 内置 pypinyin 0.55.0，见 scripts/_vendor；无需 pip install，无网络请求）"
  outputs: "自包含单文件 HTML（UTF-8、内嵌 CSS、无外部资源）；可选 PDF，需执行环境装有 Chrome/Chromium/Edge"
---

# 中文拼音注音排版（chinese-pinyin-typesetting）

把一段中文（古诗/儿歌/课文/短文/识字材料）转成**专业教材风格的注音 HTML**：
每个汉字上方是带声调的拼音（ā á ǎ à、ü、轻声齐全），诗句居中基线对齐，
A4 打印无截断，手机阅读无横向溢出。

## 执行契约（标准 Python CLI，唯一调用方式）

本 Skill 的全部能力通过一个标准命令行入口提供，**任何能执行 Python ≥3.10
的环境**（本地终端、代码沙箱、Agent 的代码执行工具）用法完全一致：

```bash
python scripts/generate.py --spec spec.json --out 输出.html
python scripts/generate.py --from-html 上次.html --override '<JSON>' --set k=v --out 新.html
python scripts/generate.py --text "《静夜思》
李白
床前明月光，疑是地上霜。
举头望明月，低头思故乡。" --out 静夜思.html
python scripts/generate.py --text-file poem.txt --out poem.html
```

约定：

- 脚本依赖全部内置（`scripts/_vendor/pypinyin`），**无需 pip install**，无网络请求；
- stdout 输出 UTF-8 JSON 摘要（`ok`、`review`、`notes` 等，见下）；退出码 0/2；
- 输出 HTML 写入 `--out` 指定路径（目录不存在会自动创建），缺省按标题命名于当前目录；
- 首次运行约 2-5 秒（加载内置词典），建议执行超时 ≥60 秒；正文建议 ≤3000 字。

Agent 的职责是：理解用户需求 → 准备 spec → 以标准方式执行上述 CLI →
把生成的文件交付用户。本 Skill 不依赖任何特定 Agent 的 API、MCP 或外部服务。

## 何时使用 / 不使用

**使用**：加拼音、注音、注音排版、拼音版古诗/课文、默写练习、看拼音写汉字、
背诵卡、识字卡、给孩子的拼音材料、A4 打印版注音文档。

**不使用**：只要纯拼音文本（不带排版）→ 直接回答即可；音频朗读（TTS）→ 用
宿主的语音合成能力；批量汉字转拼音数据 → 本 Skill 面向"可打印文档"。
**用户只给诗名不给正文时，必须先从可靠来源取得诗文**（自己确认会背的内容或
联网检索），**绝不能让拼音引擎凭空生成诗句**。

## 输入：spec JSON

```json
{
  "title": "静夜思",
  "dynasty": "唐",
  "author": "李白",
  "text": "床前明月光，疑是地上霜。\n举头望明月，低头思故乡。",
  "template": "auto",
  "mode": "both",
  "overrides": [],
  "annotate_title": true,
  "annotate_author": false,
  "han_size": 32,
  "pinyin_ratio": 0.55,
  "page": "A4",
  "margin_mm": 18,
  "font": "kai",
  "tone_sandhi": "yi_bu",
  "footer": ""
}
```

- 只有 `text` 必填，其余全部有默认值；短文本可用 `--text`/`--text-file`
  （自动识别《标题》行与"李白"/"[唐] 孟浩然"作者行）。
- 完整字段表、合法值与 CLI 参数：阅读本 Skill 目录下的 `references/spec.md`。

## 模板与模式选择

**template**：`auto`（默认，行短多行→poem，否则 reading）｜`poem` 古诗背诵版
（一句一行居中、标题朝代作者独立、五言/七言/长短句自适应字号）｜`reading`
课文阅读版（保留段落、自动换行、中英数混排）｜`worksheet` 默写练习版
（姓名/日期/得分栏 + 每句田字格书写行）。儿歌、识字卡、古诗默写用 worksheet。

**mode**（对所有模板通用）：`both` 拼音+汉字｜`hanzi` 只显汉字（背诵/朗诵）｜
`pinyin` 只显拼音、汉字位为田字格（看拼音默写）｜`blank_pinyin` 汉字+拼音书写
空线（给汉字标调练习）。

用户没指定样式就用默认（auto + both + A4），**不要反复询问配置**。

## 多音字校正（重要，务必按此执行）

自动注音**不能保证 100% 正确**。脚本会：

1. 应用内置统编教材读音表（如"石径斜 xié""见牛羊 xiàn""一日还 huán""鬓毛衰 shuāi"）；
2. 对启发式判定（地/得/长/一/不 变调）和多音字输出 `review` 列表；
3. 对教材与旧读分歧的字输出 `notes`（如"衰：教材 shuāi，旧读 cuī"）。

**必须把 review/notes 简要转述给用户**（一句即可，如"衰按教材注 shuāi，
如需旧读 cuī 告诉我"），并按用户要求用 overrides 重新生成：

| 定位方式 | 写法 | 适用 |
|---|---|---|
| 整体索引 | `{"index": 6, "pinyin": "cuī", "expect": "衰"}` | 用户给了明确位置（0 起始，含标点换行的码点偏移；expect 守卫防打错） |
| 句+字序 | `{"line": 3, "char": 2, "tone": 4}` | "第三句第二个字改成四声"（行=非空行 1 起计，字=行内汉字序号） |
| 短语 | `{"phrase": "鬓毛衰", "pinyin": "bìn máo cuī"}` | 多字连改；多处出现须加 `occurrence` 或 `"all": true` |
| 单字 | `{"char": "衰", "pinyin": "cuī", "occurrence": 1}` | 同字多处须 disambiguate，否则报错防误改 |

拼音写法兼容 `cuī`/`cui1`/`lv4`；`tone` 1-5 只改声调。同一字重复出现而未指定
是哪一处时**脚本会拒绝并列出所有位置**——把位置列表转述给用户即可。
修改后用 `--from-html` 再生成，改动会持久进新文档的嵌入 spec，可继续迭代。

## 输出与 PDF

- 产物：自包含 UTF-8 HTML（任何现代浏览器直接打开；桌面阅读、手机自适应、
  Ctrl+P 即 A4 打印，无多余控件）。默认文件名如 `静夜思（注音版）.html`
  （背诵版/看拼音写汉字/注音练习按 mode 自动命名）。
- `--pdf`：调用执行环境中的 Chrome/Chromium/Edge 无头打印；环境没有浏览器时
  返回 `pdf.ok=false` 并说明原因——此时如实告知用户"HTML 可用浏览器打印为
  PDF"。**以脚本返回的 `pdf.ok` 为准，未经实测不得声称 PDF 已生成**。

## 依赖与错误处理

- 纯 Python（≥3.10），依赖全部内置，无网络、无安装步骤，整目录拷贝即可迁移。
- stdout 恒为 JSON：`ok:true` + 摘要，或 `ok:false` + `error`（中文、含定位信息），
  退出码 2。把 error 原样转述并修正输入，不要盲目重试。

## 典型请求 → CLI 对照

| 用户说 | 执行 |
|---|---|
| "给《静夜思》加拼音，做成孩子背诵的版本" | 先取得正文 → `--text`（或 spec，默认模板） |
| "把这段课文加拼音，排版成 A4" | spec：`template:"reading"`（或默认）`page:"A4"` |
| "生成《春晓》的拼音默写练习" | spec：`template:"worksheet", mode:"pinyin"` |
| "把第三句第二个字的读音改成四声" | `--from-html 上次.html --override '{"line":3,"char":2,"tone":4}'` |
| "汉字放大点，拼音缩小点" | `--from-html 上次.html --set han_size=36 --set pinyin_ratio=0.38` |
| "不要拼音，再来一份背诵版" | `--from-html 上次.html --set mode=hanzi` |

## 质量边界（如实向用户说明）

自动注音按词语上下文 + 教材读音表 + 变调规则处理，绝大多数常见内容可靠，
但**不承诺全对**：生僻字、罕见人名、异读词、古今音争议仍需人工核对
（review 列表就是核对清单）。三上声连读变调、儿化等未建模，按教材惯例标注。
