# AGENTS.md

> **本文件的唯一职责**：给出硬约束与文档指针。
> **不属于本文件**：项目知识、设计理由、教程步骤、参数数值——一律放在 `docs/` 里，此处只放链接。
> 长度上限 120 行。任何代理或新成员在改动本仓库前必须先读完本文件。

---

## 1. 这个项目是什么

**《带型》（StripDesign）** —— 面向大豆玉米带状复合种植的**行带结构设计与光能利用分析系统**。

输入地块与农艺参数，输出推荐带型（行比 / 带宽 / 行向）、光截获分布可视化、土地当量比（LER）。

**当前阶段：阶段一 · Demo**（把核心想法做成可演示的原型，验证路线可行）。
阶段划分与判据见 [`docs/BASELINE.md`](docs/BASELINE.md)。

---

## 2. 硬约束（不可协商）

**必须做**

- **MUST** 辐射传输使用**成熟开源模型**，禁止自研光线追踪内核。
- **MUST** 计算与渲染分离：物理量由数值模型产出，渲染器只负责表现。
- **MUST** 每个农艺参数登记出处；无出处的数值不得进入代码。
- **MUST** 任何临时简化登记到 `docs/DESIGN.md` 的「临时近似登记表」，并写明何时替换。
- **MUST** 每个模块开工前先写**可证伪的判据**，判据不通过不得调参掩盖。

**禁止做**

- **MUST NOT** 宣称"精确预测产量"。只能说"相对比较与情景分析"。
- **MUST NOT** 用渲染亮度论证物理量（Cycles 的 radiance ≠ PAR）。
- **MUST NOT** 用手工调色替代计算结果的可视化。
- **MUST NOT** 提交密钥、令牌、个人数据、来源不明的数据集。
- **MUST NOT** 把阶段二的内容提前到阶段一做（见 `docs/BASELINE.md` 的范围清单）。

---

## 3. 效力与冲突

```
AGENTS.md 硬约束  >  docs/BASELINE.md  >  docs/TASKS.md  >  其余文档  >  代码注释
```

低层与高层冲突时**高层胜出**，并在 `docs/TASKS.md` 立一条修正任务。

需要例外时：在 `docs/TECH-STACK.md` 的「决策记录」节新增一条，说明违反哪条、为什么、何时回退。
**涉及第 2 节"科学诚实"类的约束，任何理由都不构成例外。**

---

## 4. 改动前必读什么

| 要改的东西 | 先读 |
|---|---|
| 任何东西 | 本文件 |
| **刚接手 / 第一次接远程仓库** | [`docs/HANDOVER.md`](docs/HANDOVER.md) |
| 做什么 / 不做什么 | [`docs/BASELINE.md`](docs/BASELINE.md) |
| 今天干什么 | [`docs/TASKS.md`](docs/TASKS.md) |
| 坐标系、角度、单位 | [`docs/CONVENTIONS.md`](docs/CONVENTIONS.md) ⚠️ 最容易错 |
| 物理模型、算法 | [`docs/DESIGN.md`](docs/DESIGN.md) |
| 参数取值 | [`docs/PARAMETERS.md`](docs/PARAMETERS.md) |
| 用哪个开源项目 | [`docs/TECH-STACK.md`](docs/TECH-STACK.md) |

---

## 5. 工具链

- Python **3.11+**，包管理用 `uv`
- 前端 TypeScript + Vite + Three.js，包管理用 `pnpm`
- 格式化：Python 用 `ruff`；前端用 `biome`
- 测试：Python 用 `pytest`；前端用 `vitest`
- Notebook 仅用于探索，**不得作为交付路径**

> 命令以 [`README.md`](README.md) 为准。若发现不一致，以 README 为准并提交一次修正。

---

## 6. 已知的坑（非显然约束）

- **坐标系符号约定是头号 bug 来源**。`docs/CONVENTIONS.md` 的定义已冻结，禁止"顺手改一下"。
- **判据 C1：南北行向的光截获必须优于东西行向**。这是免费的模型自检；算反了说明坐标系错了，**不要靠调参掩盖**。
- **LER 的分子分母必须用同一个模型算**（单作基准也要跑本模型），否则比较无效。
- **阶段一允许临时近似，但必须登记**。登记过的近似在演示时要口头说明。

---

## 7. 文档地图

```
AGENTS.md            本文件：硬约束 + 指针
README.md            项目说明 + 怎么跑
CHANGELOG.md         变更流水
docs/HANDOVER.md     交接与开工准备（接远程仓库、git 身份、首次提交）
docs/BASELINE.md     长任务基线：阶段划分、范围、判据、假设
docs/TASKS.md        当前任务 + 任务池（唯一真相源）
docs/DESIGN.md       设计 + 科学原理 + 假设 + 临时近似登记
docs/CONVENTIONS.md  坐标系与单位（冻结）
docs/PARAMETERS.md   参数取值 + 出处
docs/TECH-STACK.md   开源技术选型 + 决策记录
```

---

## 8. 更新本文件的条件

只在**硬约束或指针变化**时更新。新增知识请写入 `docs/` 对应文件，然后在此处加一行指针。
