# 开发维护规范

目的：防止"修复一个问题、破坏其他功能"。改代码前先读本文相关条目，
改完按回归协议验证；发现新的重要边界或回归，补录进来（不为完善文档而加规则）。
每季度简单核对一次本文与代码是否一致。不冻结实现，但既有功能不能无故退化。

## 模块职责（唯一维护份：本仓库）

| 文件 | 职责 | 改动影响面 |
|---|---|---|
| `scripts/generate.py` | 唯一 CLI：spec 装载/修补、模板选择、PDF 导出、结果 JSON | 全部出口行为 |
| `scripts/pronunciation.py` | 注音引擎：分词注音、教材读音、overrides 四定位 | 所有拼音正确性 |
| `scripts/renderer.py` | 版面决策（行组织/字号/页数/分页结构）+ HTML 渲染 | 所有版面行为 |
| `templates/` | base.css 共享排版 + 三模板骨架；生成时**内联**进 HTML | 全部渲染 |
| `tests/` | 单测（63）+ browser_check（33 项）+ pdf_check（真 PDF 体检） | 回归判据 |

## 不可随意改变的既有行为（不变量）

1. **输出契约**：stdout 恒为 JSON、退出码 0/2；HTML 自包含、无外部资源、
   内嵌 spec（`id="cpt-spec"`）支撑 `--from-html` 迭代。
2. **拼音对应**：每个汉字的注音单元（inline-flex ruby，汉字下/拼音上）
   逐字对应、居中对齐、声调完整；任何版面改动不得破坏对应关系
   （pdf_check 的 pinyin 检查 ≥90%）。
3. **折行只在小句边界**：诗行排版断点仅句读后；整行无内部句读的超宽行
   依次降级：开启标点（《（前）→ 字间。句尾数字孤行（"未磨。"式）是
   回归失败。
4. **标题绝不孤立成页**：`header.hd`/`.ws-meta` 原子 + `break-after: avoid`
   黏住后文；第一节 keep 判定必须含 header 高度。
5. **行组织几何驱动**：行宽预算 = 栏宽/字号（无固定字数规则）；
   小句不可拆、源行间不可并；**优先级链：用户显式参数 > target_pages
   收缩（边距≥12mm、行距≥0.3）> 栏宽硬约束（缩字下限 10pt）>
   默认 floor（max(han_size×0.55, 10)）> ABS_MIN 10pt**。窄栏宁可缩字
   保完整小句，不允许字间折断。
6. **页数自洽**：字号二分求解的 fits 判据与 `pages_est` 必须同源
   （历史上 +0.5pt 容差曾造成"可行解页数估 2"的矛盾）。
7. **末页不孤行**：flow 节末两行 `.widow-keep` 成组（结构性保证，
   不依赖 Chromium 行为）。
8. **离群豁免**：小句宽 > 1.35×全体小句 P75 的长行（如合集长标题行）
   不钳制全局字号，自身行内折行。
9. **双栏语义**：节不跨栏（`body.cols-2 .stanza:not(.flow)`）、
   窄屏回退单栏仅限 screen（打印按纸宽评估媒体查询，A5 会误触发）。

## 关键常量（改动前先想清楚，两处同步的特别标注）

| 常量 | 值 | 位置 | 说明 |
|---|---|---|---|
| `COLUMN_GAP_K` | 2.5 | renderer.py **与 base.css `column-gap` 手工同步** | 栏宽求解与实际渲染一致 |
| `FIT_FLOOR_K` / `ABS_MIN_FS` | 0.55 / 10 | renderer.py | 默认字号下限 / 绝对下限 |
| `COMFORT_K` / `COMFORT_MIN_FS` | 0.45 / 12 | renderer.py | target_pages 期望字号 |
| `MARGIN_SCALES` / `GAP_SCALES` | (1,.85,.72)/(1,.85,.7) | renderer.py | 页数目标自动收缩档 |
| `CLUSTER_OUTLIER_K` | 1.35 | renderer.py | 离群行豁免阈值（×P75） |
| `BREAK_WASTE_K` | 0.6 | renderer.py | 每个分页断点的损耗估计 |
| 拼音比例默认 | 0.55 | resolve_config | 全部字号经 `--pyr` 派生 |
| row_k 系数 | pyr×1.7+1.18 | renderer.py 与 base.css `--rowh` 公式同源 | 行高模型 |

## 连带影响矩阵（改左列 → 必测右列）

| 改动 | 必测场景 |
|---|---|
| 行组织/折行逻辑 | 20 首样本 × **单栏+双栏 × 纵+横**（栏宽变化会改变合并行为） |
| 字号求解/页数 | target_pages=1/2、默认模式；pdf_check 页数 == pages_est |
| 分页 CSS（base.css 打印段） | 标题孤页、末页孤行、田字格与诗句成对、worksheet 姓名/日期/得分 |
| cell_r/units/行高公式 | 移动端钳制（--units、cqw）、首行缩进=2 注音格、窄屏 375px |
| 注音引擎/声调 | `test_yi_bu_sandhi` 必跑（曾 t+1 偏移破坏一/不变调） |
| 任何 CSS | **必须重生成 examples 再体检**（CSS 生成时内联，旧示例是陈旧产物） |
| 模板 HTML | 三模板 × 四模式冒烟 + 自包含检查（无外部资源） |

## 回归协议（每次修改后，约 10 分钟）

```bash
python -X utf8 -m pytest tests/test_pronunciation.py tests/test_rendering.py -q   # 63 项
# 改了 CSS/模板 renderer → 重生成示例：
cd examples && for f in *.html; do python -X utf8 ../scripts/generate.py --from-html "$f" --out "$f"; done && cd ..
python -X utf8 tests/browser_check.py examples/*.html                            # 33 项
# 改了版面决策/分页/折行 → 20 首长期回归样本（含《望洞庭》《忆江南》原始缺陷样本）：
cd /tmp && python -X utf8 <repo>/scripts/generate.py --spec <repo>/tests/fixtures/gushi20.json \
  --set template=poem --out g1.html --pdf                       # A4 纵单
python -X utf8 <repo>/scripts/generate.py --from-html g1.html --set columns=2 --out g2.html --pdf
python -X utf8 <repo>/scripts/generate.py --from-html g1.html --set landscape=true --out g3.html --pdf
python -X utf8 <repo>/tests/pdf_check.py g1.html g2.html g3.html   # 页数/标题/字号/拼音/孤尾
```

pdf_check 五项全绿才算过；`pages_hanzi` 分布对比上一次提交可发现分页退化。

## 已知暂缓（勿顺手修）

- `text-align: justify` 对原子盒行无效（右缘参差）——用户明示暂缓，
  待专门任务。

## 维护纪律

1. 改前：读本文相关不变量与连带影响矩阵；
2. 改后：跑回归协议对应档位；
3. 新发现的重要边界/回归问题：补录到本文（或不变量、或矩阵），
   并加进测试；
4. 每季度：核对本文常量表与代码一致、回归样本仍全绿。
