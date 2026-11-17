# 中文拼音注音排版

**把古诗、课文和短文，变成适合阅读、背诵和打印的拼音注音文档。**

每个汉字上方自动标注带声调的汉语拼音。支持古诗排版、课文阅读、默写练习，也能按 A4 纸张和指定页数自动调整版面。

[English](README_EN.md) · [查看示例](examples/) · [Agent 使用说明](SKILL.md)

## 能做什么？

- **给汉字加拼音**：逐字标注声调，结合词语上下文处理常见多音字，并内置部分教材读音。
- **让古诗排得自然**：绝句可以一句一行，律诗和长诗可以两小句一行；根据纸张方向、栏宽和字号自动调整，不机械地按字数断行。
- **制作不同学习版本**：拼音注音版、无拼音背诵版、看拼音写汉字版、标调练习版。
- **打印和手机阅读**：支持 A4、横向或纵向、单栏或双栏；可以指定期望页数，自动优化字号、行距和边距。
- **纠正读音、继续修改**：发现多音字读错时可以指定正确读音；已经生成的文档也能修改排版后重新导出。

## 看看排版效果

仓库提供了可直接在浏览器打开的 HTML 示例：

| 想看什么 | 示例 |
| --- | --- |
| 古诗注音 | [《静夜思》](examples/1_jingyesi_poem.html) · [《春晓》](examples/2_chunxiao_poem.html) |
| 较长的古诗 | [《望庐山瀑布》](examples/3_wanglushan_poem.html) |
| 课文和短文 | [《外婆的小菜园》](examples/6_duanwen_reading.html) |
| 双栏阅读 | [双栏短文](examples/11_duanwen_twocol.html) |
| 只看汉字 | [无拼音背诵版](examples/7_huixiang_hanzi.html) |
| 拼音默写 | [看拼音写汉字](examples/5_shanxing_worksheet.html) |
| 标调练习 | [《春晓》标调练习](examples/8_chunxiao_blankpy.html) |
| 田字格默写 | [《静夜思》默写练习](examples/9_jingyesi_wshanzi.html) |

**提示**：GitHub 可能显示 HTML 源码。下载仓库后，用浏览器打开示例文件即可看到实际版式。

## 怎么使用？

这是一个供 AI Agent 调用的 Skill，也可以直接通过命令行使用。

### 1. 获取项目

[下载项目 ZIP](https://github.com/chenzhutao/chinese-pinyin-typesetting/archive/refs/heads/main.zip)，解压即可。需要 Python 3.10 或更新版本；拼音引擎已经包含在项目内，不需要另外安装 Python 依赖。

### 2. 让 AI Agent 使用

将整个项目文件夹放进所用 Agent 的 Skills 目录，并让 Agent 按照 [SKILL.md](SKILL.md) 调用。

例如，你可以直接提出：

> 给《静夜思》加拼音，排成适合小学生背诵的 A4 文档。

> 把这首长诗排成横向 A4，尽量控制在一页内。

> 把刚才的注音版改成没有拼音的背诵版。

Agent 负责准备内容、调用脚本并交付生成文件。实际支持情况取决于 Agent 是否能够加载 Skill 并执行本地 Python。

### 3. 自己在终端使用

在项目目录下运行：

```bash
python scripts/generate.py --text "《静夜思》
李白
床前明月光，疑是地上霜。
举头望明月，低头思故乡。" --out 静夜思.html
```

生成 HTML 后直接用浏览器打开。需要无拼音版本，可以基于原文件再生成：

```bash
python scripts/generate.py --from-html 静夜思.html --set mode=hanzi --out 背诵版.html
```

HTML 文件可以直接通过浏览器打印或另存为 PDF。也支持调用本机 Chrome、Chromium 或 Edge 自动导出 PDF。

## 关于拼音准确性

工具会根据词语上下文和内置教材读音处理常见多音字，但自动注音不能保证百分之百正确。对于生僻字、古诗异读和人名，建议核对；发现错误后可以指定读音重新生成。

使用的是**汉语拼音**（如 ā、á、ǎ、à），不是注音符号（ㄅㄆㄇ）。

## 更多资料

- [SKILL.md](SKILL.md)：供 Agent 阅读的调用规范
- [完整参数说明](references/spec.md)：纸张、字号、双栏、页数目标、纠音等设置
- [维护与测试说明](references/maintenance.md)：开发者参考
- [第三方许可证](THIRD_PARTY_NOTICES.md)：内置拼音引擎与数据的许可信息

项目采用 [MIT 许可证](LICENSE)；内置第三方组件遵循各自许可证。
