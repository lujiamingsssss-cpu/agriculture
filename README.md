# 带型 · StripDesign

> **本文件的唯一职责**：说明项目是什么、现在到哪一步、怎么跑起来。
> **不属于本文件**：规则（见 `AGENTS.md`）、设计理由（见 `docs/DESIGN.md`）、参数（见 `docs/PARAMETERS.md`）。

---

## 一句话

> 在一块地上同时种玉米和大豆，**带型怎么排、朝哪个方向排，直接决定光能利用率**。
> 本项目把这件事从"凭经验"变成"可算、可看、可比较"。

---

## 为什么做

大豆玉米带状复合种植是国家主推技术，目标是"玉米不减产、多收一季豆"。
但带型（行比、带宽、行向）的选择长期依赖经验，缺乏可解释、可验证的决策工具。

核心物理事实：**带状间作的光不只从上方来，还从带的侧面斜射进来**——这造就了"边行优势"，也使得**行向**成为一个被低估的关键变量。

---

## ⚠️ 定位（先说清，避免误用）

> **它是一个「行向与光分配探索器」，不是「带型推荐器」。**

**能答**：这块地南北排还是东西排？两种排法下，矮秆大豆一天里什么时候晒到太阳、晒到多少。

**不能答**：行比 / 带宽 / 株高 / LAI —— 当前模型对这些输入**实测不响应**（改输入最大变化 ≤ 1%）。
界面上**不得**把它们做成看似可调的控件。

> 本原型**不作产量断言**，只做相对比较与情景分析。详见 [`docs/DEMO-HANDOVER.md`](docs/DEMO-HANDOVER.md) §2/§6。

---

## 当前状态

| 项 | 值 |
|---|---|
| 阶段 | **阶段一 · Demo**（基线 v0.3，**以当前状态为新计划原点**） |
| 位置 | 资产已结转，**新路线第 1 步尚未开始**（见 [`docs/TASKS.md`](docs/TASKS.md) §1） |
| 下一件事 | **T-101 太阳位置接入计算层** —— 时间维是 demo 的地基，而仓库里还没有 |
| 范围与判据 | 见 [`docs/BASELINE.md`](docs/BASELINE.md)（判据 D1–D6） |
| 🔴 阶段一**不做** | "**推荐带型**"归阶段二（依赖重做冠层表达）；阶段一不得宣称已具备推荐能力 |

### Demo 验收（6 条，缺一不可）

- [x] **D1** 能输出单时刻光分布剖面图（`scripts/make_profile_figure.py`）— v0.3 起它是**下钻视图**，不是主视觉
- [x] **D2** 光斑随输入肉眼可见地变化 ← **改由「时间 + 行向 + 地点 + 日期」驱动**（带型参数已证不响应）
- [ ] **D3** ⭐ 日变化曲线成立，且南北/东西对比可辨 ← **待 T-103**
- [x] **D4** LER 如实输出：**≈0.9995**，低于文献 1.0–1.4 —— 已登记**已知偏离**，须与数字一起报
- [ ] **D5** 3 分钟录屏能放 ← 待 T-107
- [ ] **D6** 三维演示（玉米高、大豆矮，颜色来自计算值）← **待 T-105**

### 核心数字（演示用，均已实测）

| 量 | 南北行向 | 东西行向 |
|---|---|---|
| 大豆受光 / 玉米 | **1.05**（几乎持平） | **0.22**（只剩五分之一） |

长沙 2026-09-18 南北行向、全天逐 10 分钟：**07:00 → 0.05；12:00 → 0.77；18:00 → 0.04**（东西行向全天平稳 0.28~0.63，无尖峰）。
时间维度的信号强度约为带型参数的 **244 倍** —— 这是把输入轴改为时间的原因。

> ⚠️ **口径**：1.05 / 0.22 是**单位面积吸收通量密度之比**，不是带总功率之比（带总功率比为 2.09 / 0.44）。
> ⚠️ **可复现性**：逐时数字来自**原型阶段**的临时脚本，**待 T-103 变成可一键重跑**；T-103 前引用需注明。

---

## 怎么跑

> **环境**：Python 3.11.9（`uv`）。计算后端 OptiX 8.1 GPU。
> 三维渲染另需 Blender 5.2.0（外部工具，见 [`docs/DEMO-HANDOVER.md`](docs/DEMO-HANDOVER.md) §7）。

```bash
# 环境
uv venv && uv sync

# ── 验收脚本（改动物理内核时全部都要跑）──
uv run python scripts/verify_t02_scene.py            # 场景能表达"2 行高玉米 + 4 行矮大豆"
uv run python scripts/verify_t03_radiation.py        # 逐层吸收辐射 + 分带（含能量守恒硬判据）
uv run python scripts/verify_t04_criterion_c1.py     # ⭐ 判据 C1：南北行向 > 东西行向
uv run python scripts/verify_t06_biomass.py          # 吸收辐射 → 干物质（RUE 法）
uv run python scripts/verify_t07_monoculture.py      # 单作基准（同一代码路径）
uv run python scripts/verify_t08_ler.py              # LER 计算
uv run python scripts/verify_t09_strip_comparison.py # 批量带型对比

# ── 出图（产物写入 out/，已被 .gitignore 忽略）──
uv run python scripts/make_profile_figure.py         # D1：剖面吸收辐射热力图（南北 + 东西各一张）
```

场景配置文件在 `scenarios/`，格式说明见 [`scenarios/README.md`](scenarios/README.md)。
产物写入 `out/`，可随时重跑生成。
路线图与当前位置见 [`docs/TASKS.md`](docs/TASKS.md) §1–§2。

---

## 文档导航

| 我想知道… | 去哪 |
|---|---|
| **刚接手 / 怎么接上远程仓库** | [`docs/HANDOVER.md`](docs/HANDOVER.md) |
| **演示要交什么 / 怎么出图出三维 / 提交卫生** | [`docs/DEMO-HANDOVER.md`](docs/DEMO-HANDOVER.md) |
| 这个仓库的规矩 | [`AGENTS.md`](AGENTS.md) |
| 项目边界、阶段、判据 | [`docs/BASELINE.md`](docs/BASELINE.md) |
| **现在在哪一步 / 接下来做什么** | [`docs/TASKS.md`](docs/TASKS.md) §1–§2 |
| 为什么这么设计 / 物理原理 / 已知近似 | [`docs/DESIGN.md`](docs/DESIGN.md) |
| 坐标系与单位 | [`docs/CONVENTIONS.md`](docs/CONVENTIONS.md) |
| 参数取值与出处 | [`docs/PARAMETERS.md`](docs/PARAMETERS.md) |
| 用了哪些开源项目 | [`docs/TECH-STACK.md`](docs/TECH-STACK.md) |

---

## 团队

3 人，分工见 [`docs/TASKS.md`](docs/TASKS.md) §8。

---

## 许可

待定。依赖许可登记见 [`docs/TECH-STACK.md`](docs/TECH-STACK.md) §7。
⚠️ `pyhelios3d` 核心为 **GPL-2.0（有传染性）**，分发前必须处理。
