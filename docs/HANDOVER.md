# 交接与开工准备（HANDOVER）

> **本文件的唯一职责**：让任何人（或任何 AI 代理）在 10 分钟内完成**开工第一步**——把本地项目接上远程仓库。
> **不属于本文件**：项目设计（→ `DESIGN.md`）、任务内容（→ `TASKS.md`）、技术选型（→ `TECH-STACK.md`）。

| 项 | 值 |
|---|---|
| 文档版本 | v1.0 |
| 编写日期 | 2026-09-18 |
| 适用对象 | 团队成员、接管此项目的开发者、AI 代理 |
| 预计耗时 | 10 分钟 |

---

## §1 已确定的决策（开工前已拍板，不再讨论）

| # | 决策项 | 结论 | 决定日期 |
|---|---|---|---|
| 1 | 远程仓库 | `https://github.com/lujiamingsssss-cpu/agriculture` | 2026-09-18 |
| 2 | 仓库可见性 | **Public（保持公开）** | 2026-09-18 |
| 3 | 默认分支 | `main` | 2026-09-18 |
| 4 | 提交身份 · name | `lujiamingsssss-cpu` | 2026-09-18 |
| 5 | 提交身份 · email | `264750569+lujiamingsssss-cpu@users.noreply.github.com` | 2026-09-18 |
| 6 | 首次提交信息 | 见 §5 | 2026-09-18 |

> **为什么用 GitHub 匿名邮箱**：不泄露真实邮箱，同时 commit 能正确关联到 GitHub 账号。
> 其中 `264750569` 是该账号的 GitHub user id（来自 GitHub API），这是官方 noreply 格式。
> 若该格式不被接受，退回旧格式：`lujiamingsssss-cpu@users.noreply.github.com`。

---

## §2 环境现状（2026-09-18 实测）

| 项 | 实测值 | 状态 |
|---|---|---|
| git 版本 | `2.53.0.windows.2` | ✅ 可用 |
| 本地仓库 | `F:\相生相克` — **尚未初始化** | ⏳ 待处理 |
| 远程仓库 | 已创建，**完全为空**（`size: 0`） | ✅ 无冲突风险 |
| `user.name` | `你的名字`（占位符） | ⚠️ **必须先改** |
| `user.email` | `you@example.com`（占位符） | ⚠️ **必须先改** |
| `init.defaultBranch` | 未设置 | ⚠️ 用 `git init -b main` 显式指定 |
| 代理 | 未配置 | ℹ️ 若推送慢，见 §7 |

> ⚠️ **最容易出错的一步**：如果先 commit 再改身份，第一条提交的作者会永远显示为"你的名字"。
> 所以命令顺序是：**先设身份 → 再 init → 再 commit**。

---

## §3 开工第一步：命令序列

> 逐条执行。第 4 步之后我会（或你）先检查待提交内容，再执行第 5 步。

```bash
# ── 1. 设置提交身份（关键：必须在 commit 之前）──
git config --global user.name  "lujiamingsssss-cpu"
git config --global user.email "264750569+lujiamingsssss-cpu@users.noreply.github.com"

# 确认
git config --global user.name
git config --global user.email

# ── 2. 初始化本地仓库 ──
cd F:\相生相克
git init -b main

# ── 3. 接上远程 ──
git remote add origin https://github.com/lujiamingsssss-cpu/agriculture.git
git remote -v          # 确认

# ── 4. 暂存并检查（先看，后提交）──
git add .
git status             # ⚠️ 必须人工过一遍：确认没有多余文件、没有密钥
git diff --cached --stat

# ── 5. 首次提交 ──
git commit -m "docs: 建立项目文档基线"

# ── 6. 推送 ──
git push -u origin main
```

---

## §4 提交内容白名单 / 黑名单

### ✅ 应该被提交（当前共 11 个文件）

```
.gitignore
AGENTS.md
README.md
CHANGELOG.md
docs/BASELINE.md
docs/TASKS.md
docs/DESIGN.md
docs/CONVENTIONS.md
docs/PARAMETERS.md
docs/TECH-STACK.md
docs/HANDOVER.md      ← 本文件
```

### ❌ 绝不能被提交

| 类别 | 说明 | 是否已被 .gitignore 拦住 |
|---|---|---|
| 密钥 / 令牌 / `.env` | 一旦泄露不可撤回 | ✅ 已拦 |
| 原始数据 `data/raw/` | 体积大、可能有授权限制 | ✅ 已拦 |
| 中间数据 `data/interim/` | 可再生，不入库 | ✅ 已拦 |
| 产物 `out/`、图片、视频 | 仓库膨胀 | ✅ 已拦 |
| Blender 备份 `*.blend1` | 噪音 | ✅ 已拦 |
| **未公开的农艺 / 气象数据** | 版权与授权风险 | 🔴 **需人工判断** |
| **用户访谈记录、个人信息** | 隐私合规 | 🔴 **需人工判断** |
| **未核实出处的参数数值** | 科学诚实红线 | 🔴 **需人工判断** |

> 后三条 `.gitignore` 拦不住，**只能靠 `git status` 时人工过一遍**。
> 本项目现在是 **Public 仓库**，这条尤其重要（见 `AGENTS.md` 硬约束）。

---

## §5 首次提交信息

```
docs: 建立项目文档基线

- AGENTS.md            硬约束与文档指针
- docs/BASELINE.md     两阶段基线（阶段一 Demo / 阶段二 比赛级产品）
- docs/TASKS.md        当前任务 + 16 条颗粒化任务卡 + 关键路径
- docs/DESIGN.md       设计、物理原理、8 条假设、临时近似登记表
- docs/CONVENTIONS.md  坐标系与单位（已冻结）
- docs/PARAMETERS.md   参数取值与出处登记
- docs/TECH-STACK.md   开源技术选型 + 决策记录 DR-01~05
- docs/HANDOVER.md     交接与开工准备
```

**若用一行版本**：`docs: 建立项目文档基线`

---

## §6 完成判据（怎么知道第一步做完了）

- [ ] `git config --global user.name` 输出 `lujiamingsssss-cpu`
- [ ] `git config --global user.email` 输出 `264750569+lujiamingsssss-cpu@users.noreply.github.com`
- [ ] `git remote -v` 显示 `origin` 指向 `.../agriculture.git`
- [ ] `git log --oneline` 有一条提交，作者是 `lujiamingsssss-cpu`
- [ ] 浏览器打开 `https://github.com/lujiamingsssss-cpu/agriculture` 能看到 11 个文件
- [ ] `git status` 显示 `working tree clean`

---

## §7 认证与账号提醒

### 7.1 推送认证

`git push` 需要凭据。两条路：

| 走法 | 说明 |
|---|---|
| **A. 交互式登录**（推荐） | 直接 `git push`，Windows 会弹出 Git Credential Manager 浏览器登录窗口 |
| **B. Personal Access Token** | 在 GitHub → Settings → Developer settings → Tokens 生成，作为密码使用 |

> **凭据不要交给 AI 代理**。让代理做到第 5 步（commit），推送由本人执行。

### 7.2 ⚠️ 双重验证（2FA）截止日期

GitHub 已提示：**2026 年 10 月 31 日前必须启用两步验证**，否则账号将受到操作限制。

- 今天：2026-09-18，**距截止约 6 周**
- 建议**尽早开启**（Settings → Password and authentication → Two-factor authentication）
- 开启 2FA 后，**HTTPS 推送需要 Personal Access Token**（不能用账号密码）

> 这件事与项目无关，但会在你最忙的时候卡住你。**现在就顺手开掉。**

### 7.3 网络

未配置代理。若 `git push` 超时或极慢，可在**本仓库内**（不要全局）配置：

```bash
# 如果你的代理端口是 7890，按实际情况改
git config http.proxy http://127.0.0.1:7890
git config https.proxy http://127.0.0.1:7890
```

---

## §8 第一步做完之后

**下一步是 `TASKS.md` 里的 `T-01`：安装并跑通候选开源辐射模型。**

原因：`BASELINE.md` §6 把 **A2（开源模型能否处理条带冠层）** 定为当前最高风险。
A2 不成立 → 整条技术路线要重估。**所以先验证它。**

---

## §9 交接清单（若换人接手）

新接手者需要知道的事，按顺序：

1. 读 [`AGENTS.md`](../AGENTS.md) —— 硬约束（尤其"科学诚实"那条）
2. 读 [`BASELINE.md`](BASELINE.md) §2–§3 —— 现在只做阶段一 Demo，别碰阶段二
3. 读 [`TASKS.md`](TASKS.md) —— 当前任务是什么
4. 读 [`CONVENTIONS.md`](CONVENTIONS.md) —— 坐标系（改之前先问）
5. 完成本文件 §3 的命令序列（如果还没接上远程）
6. 开工

**还没定的事**（接手者需要知道）：团队成员分工未定；`PARAMETERS.md` 里所有参数都还是「待核实」；技术选型待 `T-01` 实测决定。
