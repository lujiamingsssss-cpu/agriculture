# Changelog

> **本文件的唯一职责**：记录变更流水。
> **不属于本文件**：任何解释、理由、讨论——理由写在对应文档或决策记录里，此处只留一行结果。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。
版本语义遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

---

## [Unreleased]

### Added
- 建立精简文档体系：`AGENTS.md`、`README.md`、`docs/BASELINE.md`、`docs/TASKS.md`、`docs/DESIGN.md`、`docs/CONVENTIONS.md`、`docs/PARAMETERS.md`、`docs/TECH-STACK.md`
- `docs/HANDOVER.md` 交接与开工准备：远程仓库信息、git 身份、首次提交流程、白/黑名单、2FA 提醒
- 定义阶段一（Demo）验收判据 D1–D5
- 定义核心自检判据 **C1**：南北行向光截获 > 东西行向
- 冻结坐标系与符号约定（`docs/CONVENTIONS.md`）
- 建立临时近似登记机制（`docs/DESIGN.md` 附录 A）
- [T-01] 建立 Python 3.11 环境（`uv` + `pyproject.toml`）— 支撑库 numpy / scipy / pvlib 锁定
- [T-01] 实测候选辐射模型 — `pyhelios3d` 0.1.32 跑通 OptiX 8.1 GPU 后端；`openalea-ratp` 1.0.0 源码构建成功
- [T-02] 建立 `stripcore` 计算层骨架 — `conventions.py`（坐标系/单位落地）、`geometry.py`（条带布局）、`scenario.py`（配置加载校验）、`scene.py`（注入 pyhelios 几何）
- [T-02] 最小条带场景配置 `scenarios/m2n4_ns.json` — 2:4 / 带宽 2.4 m / 南北行向 / 固定太阳角 60°-180°
- [T-02] T-02 验收脚本 `scripts/verify_t02_scene.py` — V1–V4 判据全部通过（回读 12 行几何：4 行玉米 @2.600 m、8 行大豆 @0.700 m）
- [T-03] 冠层辐射计算模块 `stripcore/radiation.py` — PAR 波段逐层吸收辐射，分离玉米带/大豆带
- [T-03] T-03 验收脚本 `scripts/verify_t03_radiation.py` — W1–W5 判据全部通过
- [T-03] `DESIGN.md` 附录 A.1 登记 4 条 pyhelios 使用口径（光源方向语义 / 必须禁用发射 / 散射深度 / 叶层图元选择）
- [T-10] 剖面吸收辐射场模块 `stripcore/profile.py` — (u, w) 网格归集 + 热力图渲染（中文字体自适应、色标含单位、底部行位标尺）
- [T-10] 出图脚本 `scripts/make_profile_figure.py` — D1–D1e 判据全部通过，输出 `out/profile_m2n4_ns.png` 与 `out/profile_m2n4_ew.png`
- [T-06] 干物质换算模块 `stripcore/biomass.py` — RUE 法：吸收辐射 → 干物质 → 产量（逐作物）
- [T-06] 验收脚本 `scripts/verify_t06_biomass.py` — B1–B5 判据全部通过（含单位链路逐项独立重算）
- [T-06] `conventions.py` 新增 `to_ground_area_mj_m2()` 与 `MJ_PER_W_M2_HOUR` — 补齐 `radiation.py` 文档中声明但缺失的换算函数，`W/m² → MJ/m²` 换算自此集中唯一
- [T-07] 单作基准场景 `scenarios/mono_maize.json`（1:0）与 `scenarios/mono_soy.json`（0:1）
- [T-07] 验收脚本 `scripts/verify_t07_monoculture.py` — B1–B5 判据全部通过
- [T-07] `StripLayout` 放开行数为 0（`is_monoculture` / `sole_crop`），使单作基准走**同一条代码路径**
- [T-08] LER 模块 `stripcore/ler.py` — 同时给出标准口径（面积份额加权）与附注口径（比值之和）
- [T-08] 验收脚本 `scripts/verify_t08_ler.py` — L1–L6 判据全部通过
- [T-08] `DESIGN.md` 附录 A 第 15 行登记：满铺水平层 → 全截获 → **LER ≈ 1.0 为已知偏离**（机制：单位面积产量与作物密度无关）
- [T-09] 批量对比模块 `stripcore/batch.py` + 场景 `scenarios/m2n3_ns.json`、`scenarios/m4n4_ns.json`
- [T-09] 验收脚本 `scripts/verify_t09_strip_comparison.py` — S1–S7 判据全部通过
- [T-09] ⚠️ 实测：三个带型 LER 均为 0.9992/0.9994/0.9992，**模型几乎无法区分带型**（与附录 A 第 15 行同源），已如实记录
- `docs/DEMO-HANDOVER.md` 演示交接：交付物清单、**工具定位**（行向与光分配探索器）、核心数值、互动组件清单、时间滑块边界、已知边界、运行环境、三维渲染纪律、为何不用 MCP
- `docs/DEMO-HANDOVER.md` §10 提交与推送卫生**完整清单**（提交前 6 条门禁、Conventional Commits 格式、BOM 字节级校验实操、单向门、禁止入库清单、已发生事故留档、推送纪律）
- `docs/TASKS.md` §1 **当前位置**（一眼看懂：已完成 T-00~T-10，停在 T-11 之前）
- `docs/TASKS.md` §2 **路线图** + 两个决策点 D-a（输入轴改为时间/行向/地点/日期）、D-b（工具定位）
- `docs/TASKS.md` §3 **问题 ↔ 方案绑定表**（P1–P10，含"什么情况下会返修"）
- `docs/TASKS.md` 新增任务 **T-17 三维渲染（Blender headless）**、**T-18 交互演示工具（时间滑块 + 行向开关 + 地点/日期）**
- `docs/TECH-STACK.md` DR-08 **阶段一交互工具用 Streamlit**（论证这不属于"阶段二前端提前"）
- `docs/TECH-STACK.md` DR-09 **三维走 Blender headless**，砍掉 Web 三维页面；配三条渲染硬约束
- `docs/TECH-STACK.md` §7 新增 streamlit（待安装）与 Blender 5.2.0（外部工具）登记

### Changed
- ⭐ **`BASELINE.md` §3.1 与判据 D2 修订**：输入轴由"拖动滑块**切换带型**"改为"切换**时间与行向**"（带型参数实测无响应，时间信号强 244×）
- ⭐ **输入轴由"带型参数"改为"时间 + 行向 + 地点 + 日期"** — 实测行比/带宽/株高/LAI 对结果几乎无影响（≤1%），而时间维度信号强度约为带型信号的 **244 倍**
- ⭐ **工具定位锁定为「行向与光分配探索器」**，不再是"带型推荐器"；界面不得把无响应参数做成控件
- `docs/TASKS.md` 由 **535 行压缩至约 300 行**：删除重复的「当前任务」节、T-04 的 260 行长篇过程叙事、重复编号与自相矛盾的状态行；历史细节按"知识归口"移入 `DESIGN.md` 附录 A.2
- `AGENTS.md` 由 130 行压缩至 **113 行**（回到自定的 120 行上限内）；新增 §6.1 提交与推送卫生；§7 文档地图补入 `DEMO-HANDOVER.md`；§5 明确"阶段一不建前端工程"
- `docs/DESIGN.md` 附录 A 第 **8、9 行订正**：原文写"这是判据 C1 无法通过的根因"，已被 T-04 实测（C1 成立，+0.99%）推翻；真实影响是**无法体现侧向受光**
- `docs/DESIGN.md` 附录 A 第 3 行更新：太阳位置改由 `pvlib` 按"地点+日期"实时给出（日累计仍属阶段二）
- `docs/DESIGN.md` 附录 A 新增第 **16 行**（行比/带宽/株高/LAI 不响应）、第 **17 行**（`row_dir_deg` 只允许 0°/90°，连续角度能量守恒失效 1.19~2.80）
- `docs/TECH-STACK.md` DR-07 订正：原文写"Helios 不承担 C1 验证"，已被 T-04 推翻（C1 在 Helios 下成立）
- `docs/TECH-STACK.md` §3 选型结论与 §6 答辩素材同步更新（新增 Streamlit / 三维 / 行向两档 / 无响应参数四问）
- `README.md` 重写"当前状态"与"怎么跑"：D1/D2/D4 状态订正（D4 已完成）、补入**定位声明**与核心数字、逐个列出 7 个验收脚本
- `README.md` 删除不存在的 `tests/test_criterion_c1.py` 命令（仓库无 `tests/` 目录）

### Fixed
- 修复三处**文档自相矛盾**：`TASKS.md` 同时存在两个「当前任务」节并互相打架；T-04 卡片标题写"当前不通过"而正文写"已通过"；`DESIGN.md`/`TECH-STACK.md` 仍称"判据 C1 无法通过"
- 修复 `README.md` 中"LER 待 T-06~T-08"的过期状态（该三项已完成）

### Removed
- 移除 `docs/governance/`、`docs/baseline/`、`docs/explanation/`、`docs/reference/`、`docs/tutorials/`、`docs/adr/` 等分层目录，内容并入现有文件
- 文档结构由 19 个文件精简为 9 个，每个文件职责单一化
- [T-01] `TECH-STACK.md` §2.1 候选表由"资料摘抄"改为"实测结果"，并修正两处原记载错误（PyRATP 含 Fortran 核心，非"纯 Python"；PyHelios 许可定为核心 GPL-2.0 / 绑定 MIT）
- [T-01] `TECH-STACK.md` §3、§7 由"待 T-01 确定"填入实测结论与依赖登记
- [T-02] **辐射传输选定 `pyhelios3d`**，`openalea.ratp` 降为已记录备选（触发条件：无 GPU 环境或需非 GPL 分发）；备选已从环境移除
- [T-02] `DESIGN.md` 附录 A 登记 5 条临时近似（待核实参数 / 固定太阳角 / 长方体冠层近似 / 带宽整除约束）
- [T-02] `pyproject.toml` 增加 hatchling 打包配置，使 `stripcore` 可被导入
- [T-03] ⭐ **假设 A2 判定为成立** — 成熟开源辐射模型能解析条带异质性（单带内大豆行呈对称 U 形，中部 231.27 > 边缘 228.90 W/m²，极差 4.835 超出重复性噪声 2.895）
- [T-03] `stripcore/scene.py` 冠层几何由**闭盒三角网格**改为 **`addPatch` 水平叶层**（实测竖直面在 OptiX 下几乎不沉积辐射能：单盒 1904 W vs 解析 2426 W）
- [T-03] `DESIGN.md` 附录 A 第 4 行更新为水平叶层描述，并新增第 6、7 行（单面口径 / 截获量分母）

### Removed
- 移除 `docs/governance/`、`docs/baseline/`、`docs/explanation/`、`docs/reference/`、`docs/tutorials/`、`docs/adr/` 等分层目录，内容并入现有文件

---

## 记录规范

每个任务完成时追加一行：

```
- [T-XX] <做了什么> — <关键产出或结论>
```

分类只用：`Added` / `Changed` / `Fixed` / `Removed` / `Deprecated`。
