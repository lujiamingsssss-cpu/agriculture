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

## 当前状态

| 项 | 值 |
|---|---|
| 阶段 | **阶段一 · Demo** |
| 目标 | 做出一段能证明核心想法的 demo，验证路线可行 |
| 当前任务 | 见 [`docs/TASKS.md`](docs/TASKS.md) |
| 范围与判据 | 见 [`docs/BASELINE.md`](docs/BASELINE.md) |

### Demo 验收（5 条，缺一不可）

- [ ] **D1** 能对一个带型输出光分布剖面图
- [ ] **D2** 切换带型，光斑肉眼可见地变化
- [ ] **D3** 南北 vs 东西并排对比成立（核心 wow）
- [ ] **D4** 出一个 LER 数字
- [ ] **D5** 3 分钟录屏能放

---

## 怎么跑

> ⚠️ 阶段一尚在技术验证，代码骨架未建立。以下命令在 `T-01` 完成后生效。

```bash
# 环境
uv venv && uv sync

# 跑一次带型评估并出图
uv run python -m stripcore.cli --m 2 --n 4 --band-width 2.4 --row-dir 0

# ⭐ 核心自检：南北向必须优于东西向
uv run pytest tests/test_criterion_c1.py -v
```

详细步骤见 [`docs/TASKS.md`](docs/TASKS.md) 中的任务卡。

---

## 文档导航

| 我想知道… | 去哪 |
|---|---|
| **刚接手 / 怎么接上远程仓库** | [`docs/HANDOVER.md`](docs/HANDOVER.md) |
| 这个仓库的规矩 | [`AGENTS.md`](AGENTS.md) |
| 项目边界、阶段、判据 | [`docs/BASELINE.md`](docs/BASELINE.md) |
| 现在该做什么 | [`docs/TASKS.md`](docs/TASKS.md) |
| 为什么这么设计 / 物理原理 | [`docs/DESIGN.md`](docs/DESIGN.md) |
| 坐标系与单位 | [`docs/CONVENTIONS.md`](docs/CONVENTIONS.md) |
| 参数取值与出处 | [`docs/PARAMETERS.md`](docs/PARAMETERS.md) |
| 用了哪些开源项目 | [`docs/TECH-STACK.md`](docs/TECH-STACK.md) |

---

## 团队

3 人，分工见 [`docs/TASKS.md`](docs/TASKS.md) 的「分工建议」。

---

## 许可

待定。依赖许可登记见 [`docs/TECH-STACK.md`](docs/TECH-STACK.md)。
