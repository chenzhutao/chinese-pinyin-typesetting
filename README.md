# chinese-pinyin-typesetting · 简体中文汉语拼音注音排版 Skill

简体中文 | [English](README_EN.md)

**AI Agent Skill · v1.1.4 · 适配支持 Skill 加载规范与本地脚本执行的 Agent · 零第三方依赖 · MIT**

面向 AI Agent 的中文注音排版技能：把古诗、儿歌、课文、短文变成**教材风格的注音 HTML**——每个汉字上方是带声调的汉语拼音（ā á ǎ à、ü、轻声齐全），诗句居中基线对齐，A4 打印不截断，手机阅读不横向滚动。注音体系是 Hanyu Pinyin（汉语拼音，中国大陆简体中文的标准注音方案），**不是**台湾注音符号 Zhuyin / Bopomofo（ㄅㄆㄇ），也不支持注音符号。

它**跨 Agent 通用**：目录里的 [SKILL.md](SKILL.md) 是 Agent 阅读的使用规范，CLI 是唯一执行入口，不依赖任何特定 Agent 的 SDK、API 或外部服务——支持 Skill 加载、能本地执行 Python ≥3.10 脚本的 Agent（如 Claude Code、ZCode）都能用；人也可以在终端直接用。

## 核心功能

- **逐字注音**：拼音标在汉字正上方，按词语上下文消歧，声调符号齐全
- **教材读音内置**：统编教材审定读音自动应用（如"石径斜 xié""一日还 huán"）；"一 / 不"变调按教材标注，可关闭
- **多音字提示 + 可选纠音**：可疑读音写入 `review` 清单由 Agent 转述给用户；`overrides` 可选纠正，支持按索引、按句字、按短语、按单字四种定位
- **3 模板 × 4 模式**：古诗背诵 / 课文阅读 / 默写练习 × 注音 / 只汉字 / 只拼音 / 标调练习
- **迭代再生成**：`--from-html` 从既有 HTML 恢复全部配置与纠音记录，改一个参数就出新版
- **自包含 HTML 输出**：单文件、内嵌 CSS，手机自适应，Ctrl+P 即 A4 打印，`--pdf` 可选调本机 Chrome/Edge 导出 PDF

## 效果展示

`examples/` 收录 10 个真实产物（配置内嵌、可复现）。GitHub 页面只显示源码，clone 或下载后用浏览器打开即可看到实际排版：

| 示例 | 内容 | 模板 / 模式 |
|---|---|---|
| [1_jingyesi_poem.html](examples/1_jingyesi_poem.html) | 《静夜思》古诗背诵 | poem / both |
| [2_chunxiao_poem.html](examples/2_chunxiao_poem.html) | 《春晓》古诗背诵 | poem / both |
| [3_wanglushan_poem.html](examples/3_wanglushan_poem.html) | 《望庐山瀑布》古诗背诵 | poem / both |
| [4_huixiang_cuui.html](examples/4_huixiang_cuui.html) | 《回乡偶书》，"衰"人工纠正为旧读 cuī | poem / both + override |
| [5_shanxing_worksheet.html](examples/5_shanxing_worksheet.html) | 《山行》看拼音写汉字 | worksheet / pinyin |
| [6_duanwen_reading.html](examples/6_duanwen_reading.html) | 《外婆的小菜园》原创短文 | reading / both |
| [7_huixiang_hanzi.html](examples/7_huixiang_hanzi.html) | 《回乡偶书》无拼音背诵版 | poem / hanzi |
| [8_chunxiao_blankpy.html](examples/8_chunxiao_blankpy.html) | 《春晓》标调练习 | worksheet / blank_pinyin |
| [9_jingyesi_wshanzi.html](examples/9_jingyesi_wshanzi.html) | 《静夜思》田字格默写 | worksheet / hanzi |
| [10_woiuiqing_reading.html](examples/10_woiuiqing_reading.html) | 《我对爱情的理解》现代短文 | reading / both |

## 安装

Python ≥3.10 即可，拼音引擎已内置在 `scripts/_vendor/`（无需 pip install，运行时不联网）：

```bash
git clone https://github.com/chenzhutao/chinese-pinyin-typesetting.git
# 或下载 Release ZIP 解压：
# https://github.com/chenzhutao/chinese-pinyin-typesetting/releases/tag/v1.1.4
```

- **给 Agent 用**：整个目录放进 Agent 的技能/Skills 目录（路径以所用 Agent 文档为准，如 `~/.claude/skills/`）
- **当命令行工具用**：任意位置，直接运行下面的命令
- `--pdf` 需要本机装有 Chrome / Chromium / Edge；Windows 控制台报编码错误时用 `python -X utf8 ...` 运行

## 快速开始

```bash
python scripts/generate.py --text "《静夜思》
李白
床前明月光，疑是地上霜。
举头望明月，低头思故乡。" --out 静夜思.html

# 换个形态再来一份（如只留汉字的背诵版）
python scripts/generate.py --from-html 静夜思.html --set mode=hanzi --out 静夜思（背诵版）.html
```

stdout 返回 JSON 摘要（含 `review` 多音字提示），退出码 0/2。内容也可用 `--text-file` 或 `--spec` 传入。**完整 CLI 参数、spec 字段表、纠音写法见 [SKILL.md](SKILL.md) 与 [references/spec.md](references/spec.md)。**

## 模板与显示模式

| 模板 | 用途 |
|---|---|
| `poem` | 古诗：一句一行居中，标题/朝代/作者独立，五言七言自适应字号 |
| `reading` | 课文：保留段落、自动换行，中英数混排 |
| `worksheet` | 默写：姓名/日期/得分栏 + 田字格书写行 |

显示模式（所有模板通用）：`both` 注音（默认）· `hanzi` 只汉字（背诵）· `pinyin` 只拼音（看拼音写汉字）· `blank_pinyin` 标调练习。字号、纸张、字体、边距等版面参数见 [references/spec.md](references/spec.md)。

## 多音字纠音

自动注音不保证全对：可疑读音写入 `review`，教材与旧读分歧写入 `notes`（如"衰：教材 shuāi，旧读 cuī"），由 Agent 一句话转述给用户；默认产物可直接使用，用户想改读音时才用 `overrides`（可选机制，四种定位写法见 [references/spec.md](references/spec.md)），`--from-html` 迭代后纠音记录保留。生僻字、罕见人名、古今音争议建议人工核对。

## 版本信息

当前 **v1.1.4**（2026-11-14）· 项目自身：MIT（[LICENSE](LICENSE)，仅适用于本项目原创代码与内容）；内置 pypinyin 及拼音数据适用各自许可证（详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)）· 发布包：[Release v1.1.4](https://github.com/chenzhutao/chinese-pinyin-typesetting/releases/tag/v1.1.4)

- v1.1.4：拼音默认字号提升至汉字的 55%
- v1.1.3：修复 phrase + all 定位纠音崩溃；首个公开版本

仓库自带 43 项单元测试与 30 项浏览器体检（`tests/`）。
