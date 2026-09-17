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

### Changed
- 文档结构由 19 个文件精简为 9 个，每个文件职责单一化

### Removed
- 移除 `docs/governance/`、`docs/baseline/`、`docs/explanation/`、`docs/reference/`、`docs/tutorials/`、`docs/adr/` 等分层目录，内容并入现有文件

---

## 记录规范

每个任务完成时追加一行：

```
- [T-XX] <做了什么> — <关键产出或结论>
```

分类只用：`Added` / `Changed` / `Fixed` / `Removed` / `Deprecated`。
