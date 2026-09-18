"""坐标系、角度与单位约定。

本模块是 `docs/CONVENTIONS.md` 的**唯一代码落点**。

⚠️ `docs/CONVENTIONS.md` 的定义**已冻结**。本模块的符号约定（尤其 §4.4 剖面法向）
是头号 bug 来源，**禁止"顺手改一下"**。如需变更，走 `CONVENTIONS.md` §8 的变更流程。

单位纪律（`CONVENTIONS.md` §6）：变量名必须带单位后缀（`_m` / `_deg` / `_rad`），
禁止 `angle` / `x` / `k` 这类单位不明的名字。
"""

from __future__ import annotations

import math

# --------------------------------------------------------------------------
# 具名换算常数（CONVENTIONS.md §5 强制：必须写在本模块，禁止散落）
# --------------------------------------------------------------------------

M2_PER_MU: float = 666.67
"""1 亩 = 666.67 m²。 [约定: docs/CONVENTIONS.md §5]"""

DEG_PER_RAD: float = 180.0 / math.pi
"""弧度 → 度。 [约定: docs/CONVENTIONS.md §5]"""

RAD_PER_DEG: float = math.pi / 180.0
"""度 → 弧度。 [约定: docs/CONVENTIONS.md §5]"""

# --------------------------------------------------------------------------
# 世界坐标系（CONVENTIONS.md §1）
#   x 向东为正，y 向北为正，z 垂直向上为正；角度绕 z 轴逆时针为正。
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# 剖面坐标系（CONVENTIONS.md §2）
#   u 水平、垂直于行向；w 垂直向上（= 世界坐标 z）；v 沿行向（均匀，被积分掉）。
# --------------------------------------------------------------------------


def sun_unit_vector(elev_deg: float, azim_deg: float) -> tuple[float, float, float]:
    """太阳单位向量（世界系）。 [约定: docs/CONVENTIONS.md §4.2]

    sx = cos(elev)·sin(azim)   东向
    sy = cos(elev)·cos(azim)   北向
    sz = sin(elev)             垂直

    Args:
        elev_deg: 太阳高度角 [度]，地平线以上为正。
        azim_deg: 太阳方位角 [度]，**从正北顺时针**（0=北, 90=东, 180=南, 270=西）。

    Returns:
        (sx, sy, sz)，模长为 1。
    """
    elev_rad = elev_deg * RAD_PER_DEG
    azim_rad = azim_deg * RAD_PER_DEG
    return (
        math.cos(elev_rad) * math.sin(azim_rad),
        math.cos(elev_rad) * math.cos(azim_rad),
        math.sin(elev_rad),
    )


def row_unit_vector(row_dir_deg: float) -> tuple[float, float, float]:
    """行向单位向量（世界系）。 [约定: docs/CONVENTIONS.md §4.3]

    r = ( sin(row_dir), cos(row_dir), 0 )

    Args:
        row_dir_deg: 行向 [度]，**从正北顺时针**。0° = 南北向，90° = 东西向。

    Returns:
        (rx, ry, 0.0)，模长为 1。
    """
    row_dir_rad = row_dir_deg * RAD_PER_DEG
    return (math.sin(row_dir_rad), math.cos(row_dir_rad), 0.0)


def profile_normal(row_dir_deg: float) -> tuple[float, float, float]:
    """剖面法向（世界系）。 ⚠️ 头号 bug 来源。 [约定: docs/CONVENTIONS.md §4.4]

    n = ( r.y , −r.x , 0 ) = ( cos(row_dir), −sin(row_dir), 0 )

    注意 y 分量取的是 **−r.x**（负号），不是 r.x。写反会让判据 C1 得出相反结论。

    Args:
        row_dir_deg: 行向 [度]，从正北顺时针。

    Returns:
        (nx, ny, 0.0)，模长为 1。
    """
    rx, ry, _ = row_unit_vector(row_dir_deg)
    return (ry, -rx, 0.0)


def profile_ray_direction(
    elev_deg: float, azim_deg: float, row_dir_deg: float
) -> tuple[float, float]:
    """光线在剖面内的方向。 [约定: docs/CONVENTIONS.md §4.5]

    perpComp = s · n        光线在剖面水平方向（u）的分量
    vertComp = s.z          垂直方向（w）的分量
    (dir_u, dir_w) = normalize(perpComp, vertComp)

    物理含义（CONVENTIONS.md §4.5）：
        perpComp ≈ 0  → 行向与太阳方位平行，剖面内接近垂直入射，行间受光均匀
        |perpComp| 最大 → 行向与太阳方位垂直，光线倾斜最大，前排遮挡后排

    Args:
        elev_deg: 太阳高度角 [度]。
        azim_deg: 太阳方位角 [度]，从正北顺时针。
        row_dir_deg: 行向 [度]，从正北顺时针。

    Returns:
        (dir_u, dir_w)，模长为 1。

    Raises:
        ValueError: 当光线平行于剖面（vertComp 与 perpComp 同时为 0，即太阳在地平线下）。
    """
    sx, sy, sz = sun_unit_vector(elev_deg, azim_deg)
    nx, ny, _ = profile_normal(row_dir_deg)

    perp_comp = sx * nx + sy * ny
    vert_comp = sz

    norm = math.hypot(perp_comp, vert_comp)
    if norm == 0.0:
        raise ValueError(
            "光线平行于剖面且无垂直分量（太阳位于地平线）：无法定义剖面内方向。"
            "请检查 elev_deg 是否 > 0。"
        )
    return (perp_comp / norm, vert_comp / norm)


def effective_zenith_deg(elev_deg: float, azim_deg: float, row_dir_deg: float) -> float:
    """剖面内等效天顶角 [度]。 [约定: docs/CONVENTIONS.md §4.6]

    tan(zenith_eff) = |perpComp| / vertComp

    Args:
        elev_deg: 太阳高度角 [度]。
        azim_deg: 太阳方位角 [度]，从正北顺时针。
        row_dir_deg: 行向 [度]，从正北顺时针。

    Returns:
        等效天顶角 [度]，范围 [0, 90)。

    Raises:
        ValueError: 太阳位于地平线或以下（vertComp <= 0）。
    """
    sx, sy, sz = sun_unit_vector(elev_deg, azim_deg)
    nx, ny, _ = profile_normal(row_dir_deg)
    perp_comp = sx * nx + sy * ny

    if sz <= 0.0:
        raise ValueError(
            f"太阳位于地平线或以下（sin(elev)={sz:.6f}），等效天顶角无定义。"
        )
    return math.atan2(abs(perp_comp), sz) * DEG_PER_RAD
