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

### Changed
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
