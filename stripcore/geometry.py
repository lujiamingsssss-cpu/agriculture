"""条带布局几何（阶段一二维剖面）。

对应 `docs/CONVENTIONS.md` §3「行带布局（沿 u 轴）」与 `docs/DESIGN.md` D3（简化为二维剖面）。

坐标纪律：本模块只产出 **u 坐标**（剖面内水平、垂直于行向）与高度 w（= 世界 z）。
行向 v 方向被视为统计均匀，不建模（假设 H3）。

设计约束：本模块**不依赖 pyhelios**，是纯几何计算，可独立测试。
把几何与辐射模型解耦，是 `DESIGN.md` §3「计算层不得依赖渲染层」的同一条纪律。
"""

from __future__ import annotations

from dataclasses import dataclass

# 作物类型标签。行位的 tag 由此派生，用于后续按带分离统计（T-03 需要）。
CROP_MAIZE: str = "maize"
CROP_SOY: str = "soy"


@dataclass(frozen=True)
class RowPosition:
    """一根行的剖面位置与形态标签。"""

    index: int
    """行序号，沿 u 轴从 0 递增。"""

    crop: str
    """作物类型：`CROP_MAIZE` 或 `CROP_SOY`。"""

    u_center_m: float
    """行中心在 u 轴的坐标 [m]。"""

    height_m: float
    """该行所属作物的株高 [m]。"""

    lai: float
    """该行所属作物的叶面积指数（无量纲）。"""


@dataclass(frozen=True)
class StripLayout:
    """一个带型在剖面内的几何描述。

    约定（`CONVENTIONS.md` §3）：
        row_spacing_m = band_width_m / (m + n)
        玉米带占据 u ∈ [0, m · row_spacing_m)
        大豆带占据 u ∈ [m · row_spacing_m, band_width_m)
        带在 u 方向以 band_width_m 为周期重复。

    阶段一另有临时约束：band_width_m 必须能被 (m + n) 整除（见 `DESIGN.md` 附录 A 第 3 行）。
    """

    m: int
    """玉米行数（2–4）。 [参数: docs/PARAMETERS.md §1]"""

    n: int
    """大豆行数（2–4）。 [参数: docs/PARAMETERS.md §1]"""

    band_width_m: float
    """一个完整带（玉米带 + 大豆带）的宽度 [m]。 [参数: docs/PARAMETERS.md §1]"""

    row_dir_deg: float
    """行向 [度]，从正北顺时针。0 = 南北，90 = 东西。 [参数: docs/PARAMETERS.md §1]"""

    h_maize_m: float
    """玉米株高 [m]。 ⚠️ 取自 PARAMETERS.md 默认值，状态「待核实」，已登记附录 A。"""

    h_soy_m: float
    """大豆株高 [m]。 ⚠️ 同上。"""

    lai_maize: float
    """玉米叶面积指数（无量纲）。 ⚠️ 同上。"""

    lai_soy: float
    """大豆叶面积指数（无量纲）。 ⚠️ 同上。"""

    n_bands: int = 2
    """计算域覆盖的完整带数。`CONVENTIONS.md` §3 要求 ≥ 2，以减小边界效应。"""

    def __post_init__(self) -> None:
        # 允许 m 或 n 为 0 —— 用于**单作基准**（T-07）：
        #   m=1, n=0 → 纯玉米单作；m=0, n=1 → 纯大豆单作。
        #   单作基准必须走与本模型**同一条代码路径**（`DESIGN.md` §4.5），
        #   故不能在别处另写一套单作算法，只能在此放开行数为 0。
        if self.m < 0 or self.n < 0:
            raise ValueError(f"行数不可为负：m={self.m}, n={self.n}")
        if self.m == 0 and self.n == 0:
            raise ValueError("m 与 n 不可同时为 0 —— 场景至少需要一种作物")
        if self.band_width_m <= 0.0:
            raise ValueError(f"带宽必须为正：band_width_m={self.band_width_m}")
        if self.n_bands < 1:
            raise ValueError(f"带数必须 ≥ 1，当前 n_bands={self.n_bands}")
        # 单作基准只需 1 个带（整块地单一作物，无带间边界效应）；间作要求 ≥ 2
        if not self.is_monoculture and self.n_bands < 2:
            raise ValueError(
                f"间作计算域必须覆盖至少 2 个完整带以减小边界效应，当前 n_bands={self.n_bands}"
                " [约定: docs/CONVENTIONS.md §3]"
            )
        # 玉米株高须大于大豆株高 —— 仅在两者**同时存在**时才要求（条带异质性前提）
        if self.m > 0 and self.n > 0 and self.h_maize_m <= self.h_soy_m:
            raise ValueError(
                "玉米株高必须大于大豆株高，否则不构成条带异质冠层："
                f"h_maize_m={self.h_maize_m}, h_soy_m={self.h_soy_m}"
            )
        if self.m > 0 and self.lai_maize <= 0.0:
            raise ValueError(f"玉米 LAI 必须为正：lai_maize={self.lai_maize}")
        if self.n > 0 and self.lai_soy <= 0.0:
            raise ValueError(f"大豆 LAI 必须为正：lai_soy={self.lai_soy}")
        # 阶段一临时约束：整除时行距才等于 band_width/(m+n)
        n_rows_total = self.m + self.n
        if abs(self.row_spacing_m * n_rows_total - self.band_width_m) > 1e-9:
            raise ValueError(
                "阶段一要求 band_width_m 能被 (m + n) 整除，使每行间距恰为"
                f" band_width/(m+n)。当前 band_width_m={self.band_width_m},"
                f" m+n={n_rows_total} → row_spacing_m={self.row_spacing_m}"
                " [临时近似: docs/DESIGN.md 附录 A]"
            )

    @property
    def n_rows_total(self) -> int:
        """一个带内的总行数 m + n。"""
        return self.m + self.n

    @property
    def is_monoculture(self) -> bool:
        """是否为**单作**布局（仅一种作物）。

        单作用于 T-07 的 LER 基准：`m=1, n=0` 为纯玉米、`m=0, n=1` 为纯大豆。
        基准必须走与本模型相同的代码路径（`DESIGN.md` §4.5）。
        """
        return self.m == 0 or self.n == 0

    @property
    def sole_crop(self) -> str | None:
        """单作时的作物类型；间作返回 None。"""
        if self.m > 0 and self.n == 0:
            return CROP_MAIZE
        if self.n > 0 and self.m == 0:
            return CROP_SOY
        return None

    @property
    def row_spacing_m(self) -> float:
        """行距 [m]。 [约定: docs/CONVENTIONS.md §3]"""
        return self.band_width_m / self.n_rows_total

    @property
    def domain_width_m(self) -> float:
        """计算域在 u 方向的宽度 [m] = n_bands × band_width_m。 [约定: §3]"""
        return self.n_bands * self.band_width_m

    @property
    def maize_band_width_m(self) -> float:
        """玉米带宽度 [m] = m × row_spacing_m。 [约定: §3]"""
        return self.m * self.row_spacing_m

    def u_maize_band(self) -> tuple[float, float]:
        """玉米带在 u 轴上的范围 [m]：`[0, m · row_spacing_m)`。 [约定: §3]"""
        return (0.0, self.maize_band_width_m)

    def u_soy_band(self) -> tuple[float, float]:
        """大豆带在 u 轴上的范围 [m]：`[m · row_spacing_m, band_width_m)`。 [约定: §3]"""
        return (self.maize_band_width_m, self.band_width_m)

    def row_positions(self) -> tuple[RowPosition, ...]:
        """按 `CONVENTIONS.md` §3 的图例规则计算全部行位。

        规则（与 §3 示例 `m=2, n=4, band_width=2.4` 逐步对齐）：
            带内第 i 行（i 从 0 起）中心在 u = (i + 0.5) · row_spacing_m；
            该中心落在第 b 个带（b 从 0 起）内时，整体平移 b · band_width_m；
            前 m 行为玉米，其余为大豆。

        对 §3 的示例验证：row_spacing = 0.4，
            玉米行中心 = 0.2, 0.6；大豆行中心 = 1.0, 1.4, 1.8, 2.2。
        """
        positions: list[RowPosition] = []
        index = 0
        for band in range(self.n_bands):
            offset_m = band * self.band_width_m
            for i in range(self.n_rows_total):
                is_maize = i < self.m
                positions.append(
                    RowPosition(
                        index=index,
                        crop=CROP_MAIZE if is_maize else CROP_SOY,
                        u_center_m=offset_m + (i + 0.5) * self.row_spacing_m,
                        height_m=self.h_maize_m if is_maize else self.h_soy_m,
                        lai=self.lai_maize if is_maize else self.lai_soy,
                    )
                )
                index += 1
        return tuple(positions)

    def crop_counts_per_band(self) -> tuple[int, int]:
        """一个带内的 (玉米行数, 大豆行数)，用于自检行比是否正确表达。"""
        rows = [r.crop for r in self.row_positions() if r.index < self.n_rows_total]
        return (rows.count(CROP_MAIZE), rows.count(CROP_SOY))
