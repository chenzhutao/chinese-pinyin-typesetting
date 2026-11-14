# 第三方声明 / THIRD_PARTY_NOTICES

本项目 **chinese-pinyin-typesetting** 自身采用 MIT 许可证（见 [LICENSE](LICENSE)）。
**该 MIT 许可证仅适用于本项目原创的代码与原创内容**（含 `SKILL.md`、模板、脚本、
`curated_phrases.json` 教材读音表及示例中的原创短文），**不涵盖**下列第三方依赖与数据，
它们分别适用各自的许可证：

## 1. pypinyin 0.55.0（内置副本：`scripts/_vendor/pypinyin/`）

- 许可证：**MIT**，Copyright (c) 2016 mozillazg, 闲耘 <hotoo.cn@gmail.com>
  （许可证原文随附于 `scripts/_vendor/pypinyin-0.55.0.dist-info/licenses/LICENSE.txt`）
- 上游：<https://github.com/mozillazg/python-pinyin>
- 本地改动：本项目将上游 `phrases_dict.py` 加载器扩展为在基础词典加载后合并
  项目自有的 `curated_phrases.json`（教材读音表，本项目原创内容，随项目 MIT）。

## 2. 内置拼音数据（`phrases_dict.json` / `pinyin_dict.json`）

两个词典文件随 pypinyin 0.55.0 分发。上游 python-pinyin 官方 README 声明其来源为：
"单个汉字的拼音使用 pinyin-data 的数据；词组的拼音使用 phrase-pinyin-data 的数据"。

### 2.1 pinyin_dict.json（单字拼音）

- 来源项目：[pinyin-data](https://github.com/mozillazg/pinyin-data)，**MIT**，
  Copyright (c) 2016 mozillazg
- 该项目 README 声明其数据来源包括：Unihan Database（kMandarin、kTGHZ2013、
  kHanyuPinyin、kXHC1983、kHanyuPinlu 等字段，适用 Unicode Terms of Use）、
  汉典（zdic.net）、由 CC-CEDICT 生成的单字拼音数据、以及人工修正数据。

### 2.2 phrases_dict.json（词组拼音）

- 来源项目：[phrase-pinyin-data](https://github.com/mozillazg/phrase-pinyin-data)，
  **MIT**，Copyright (c) 2017 mozillazg
- 该项目 README 声明其数据来源包括：**CC-CEDICT**（cc-cedict.org）、
  汉典网汉语词典 / 成语词典拼音数据、以及人工修正数据。

### 2.3 CC-CEDICT 的 CC BY-SA 义务

CC-CEDICT 以 **Creative Commons 署名-相同方式共享（CC BY-SA）** 许可分发
（2007 年起为 CC BY-SA 3.0，现行版本通常为 4.0；官方下载页在本声明编写时
未能直接访问核验现行版本号，**此版本号待核实**：
<https://www.mdbg.net/chindict/chindict.php?page=cc-cedict>）。据此：

- **署名**：本文件即是对 CC-CEDICT 及上述各来源的署名；再分发本项目时请保留本声明文件。
- **相同方式共享**：上述词典数据中源自 CC-CEDICT 的部分，其再分发适用
  CC BY-SA 的相同方式共享义务。

### 2.4 已知限制（如实声明）

- `phrases_dict.json` / `pinyin_dict.json` 为多来源合并后的成品数据，
  **无法逐条区分单个条目具体来自哪个来源**；本声明按各上游项目公开的
  来源说明整体署名，未做逐条核对。
- 汉典（zdic.net）抓取数据的具体授权条款，上游项目未作声明，**待核实**。

## 3. 示例内容（examples/）

- 《静夜思》《春晓》《望庐山瀑布》《山行》《回乡偶书》均为公有领域古典诗歌。
- 《外婆的小菜园》（示例 6）为本项目原创短文，随项目 MIT。
- 《我对爱情的理解》（示例 10）为项目作者本人原创作品，随项目 MIT。
