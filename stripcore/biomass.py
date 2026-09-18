"""吸收辐射 → 干物质 → 产量（RUE 法）。对应 `docs/TASKS.md` T-06。

**方法论**（`docs/DESIGN.md` §4.4）
    采用**辐射利用效率（RUE）法**，不用机理光合模型：

        ΔDM = RUE × PAR_absorbed        (g DM / MJ)
        DM  = Σ ΔDM
        Y   = DM × HI                   (HI = 收获指数)

    理由：本项目做的是**相对比较**；RUE 参数更易获取、更稳健；
    机理模型参数无法在竞赛周期内标定。

**为什么 RUE 法可以自研**（`AGENTS.md` DR-01 的界线）
    RUE 是**代数换算**，不是物理机理内核 —— 已由 `TECH-STACK.md` §2.2 裁定。
    本模块**不含**任何辐射传输计算：吸收辐射由 `stripcore.radiation` 产出。

⚠️ **绝对量纪律**（`AGENTS.md` 第 2 节 / `DESIGN.md` 附录 B 禁止用法）
    本模块输出的干物质/产量**只能用于相对比较与情景分析**，
    **不得**表述为"预测产量"。相关措辞禁令见 `DESIGN.md` 附录 B。

**单位链路**（`CONVENTIONS.md` §5，全程可核对）
    吸收通量密度 [W/m²]（`radiation.py` 输出，瞬时）
      → × 时长 [h] × 0.0036  ⇒ 能量 [MJ/m²]      （`conventions.to_ground_area_mj_m2`）
      → × RUE [g DM/MJ]       ⇒ 干物质 [g DM/m²]
      → × HI                  ⇒ 产量 [g/m²]（干重）
    换算因子集中在 `conventions.py`，本模块不出现魔法数字。

⚠️ **时序假设必须显式**（本模块最重要的纪律）
    `radiation.py` 给出的是**单一时刻的瞬时通量**。把它折算为"日累计"
    是一个**额外的物理假设**，本模块用参数 `duration_h` 强制调用方显式给出，
    并在 `DESIGN.md` 附录 A 登记。默认值 `EQUIVALENT_SUNSHINE_HOURS` 是
    阶段一原型近似，**不是**已核实参数。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from stripcore.conventions import to_ground_area_mj_m2
from stripcore.geometry import CROP_MAIZE, CROP_SOY
from stripcore.radiation import BandResult

# ── RUE 与收获指数 ──
# ⚠️ 全部取自 docs/PARAMETERS.md §4 的默认值，状态【待核实】，
#    已登记 docs/DESIGN.md 附录 A。禁止把这里的数值当成已核实参数引用。
RUE_MAIZE_G_DM_PER_MJ: float = 2.0
"""玉米辐射利用效率 [g DM/MJ]。 [参数: PARAMETERS.md §4，区间 1.5–2.5，待核实]"""

RUE_SOY_G_DM_PER_MJ: float = 1.4
"""大豆辐射利用效率 [g DM/MJ]。 [参数: PARAMETERS.md §4，区间 1.0–1.8，待核实]"""

HI_MAIZE: float = 0.50
"""玉米收获指数（无量纲）。 [参数: PARAMETERS.md §4，待核实]"""

HI_SOY: float = 0.40
"""大豆收获指数（无量纲）。 [参数: PARAMETERS.md §4，待核实]"""

EQUIVALENT_SUNSHINE_HOURS: float = 6.0
"""等效日照时长 [h]：把"单一时刻的瞬时通量"折算为"日累计能量"的**原型近似**。

⚠️ **这是阶段一最粗糙的一个假设，必须显式声明**：
    本项目目前只在**单一太阳位置**（高度角 60°、方位角 180°）下计算瞬时通量，
    并未按时间积分真实太阳轨迹。用一个等效时长折算日累计，隐含假设了
    "该时刻的瞬时通量可代表全天平均水平"。
    取 6 h 是晴天有效日照量级的原型取值；**不是**从文献核实来的参数。

    影响：全部干物质与产量的**绝对量**随之线性缩放；
    **不影响**同一时长下两行向 / 两带型之间的相对比较（那是本项目的主用途）。

    替换时点：T-06/T-07 引入 `pvlib` 逐时太阳位置并按日积分后即应替换
    （已登记 `DESIGN.md` 附录 A 第 3 行）。
"""


@dataclass
class CropBiomass:
    """单一作物的干物质与产量结果。

    ⚠️ **面积口径**：所有强度量（`absorbed_flux_w_m2`、`dry_matter_g_m2`、
    `yield_g_m2`）都相对**该作物的地面占地面积**（`row_spacing × row_length × 行数 × 带数`），
    而不是相对叶层几何面积。理由：干物质须按"单位土地面积"比较才有意义，
    而叶层面积是建模产物、会随层数变化（见 `DESIGN.md` 附录 A 第 11 行）。
    """

    crop: str
    absorbed_flux_w_m2: float
    """该作物的平均吸收通量密度 [W/m²]（相对**地面面积**，瞬时）。"""

    absorbed_energy_mj_m2: float
    """折算的日累计吸收辐射能量 [MJ/m²]（相对**地面面积**）。"""

    rue_g_dm_per_mj: float
    """所用辐射利用效率 [g DM/MJ]。"""

    hi: float
    """所用收获指数（无量纲）。"""

    dry_matter_g_m2: float
    """干物质累积 [g DM/m²]。"""

    yield_g_m2: float
    """籽粒/经济产量（干重）[g/m²] = 干物质 × HI。"""

    ground_area_m2: float
    """该作物的地面占地面积 [m²]。"""

    @property
    def yield_kg_per_mu(self) -> float:
        """产量 [kg/亩]。

        ⚠️ 仅供展示换算；**不得**据此宣称"预测产量"（`DESIGN.md` 附录 B）。
        """
        from stripcore.conventions import M2_PER_MU

        return self.yield_g_m2 * M2_PER_MU / 1000.0


@dataclass
class BiomassResult:
    """一次换算的完整结果（按作物分离）。"""

    duration_h: float
    crops: dict[str, CropBiomass]

    def total_yield_g_m2(self) -> float:
        """全部作物产量之和 [g/m²]（按各自占地面积加权的总量）。"""
        return sum(c.yield_g_m2 for c in self.crops.values())


def rue_for_crop(crop: str) -> float:
    """该作物的辐射利用效率 [g DM/MJ]。 [参数: PARAMETERS.md §4，待核实]"""
    if crop == CROP_MAIZE:
        return RUE_MAIZE_G_DM_PER_MJ
    if crop == CROP_SOY:
        return RUE_SOY_G_DM_PER_MJ
    raise ValueError(f"未知作物类型：{crop!r}（期望 {CROP_MAIZE!r} 或 {CROP_SOY!r}）")


def hi_for_crop(crop: str) -> float:
    """该作物的收获指数（无量纲）。 [参数: PARAMETERS.md §4，待核实]"""
    if crop == CROP_MAIZE:
        return HI_MAIZE
    if crop == CROP_SOY:
        return HI_SOY
    raise ValueError(f"未知作物类型：{crop!r}（期望 {CROP_MAIZE!r} 或 {CROP_SOY!r}）")


def crop_ground_area_m2(crop: str, layout, row_length_m: float) -> float:
    """该作物的地面占地面积 [m²]。

    ⚠️ **口径（修正过一次）**：
        正确口径是"该作物占的**条带宽度** × 行长 × 带数"，
        而条带宽度 = `row_spacing × 该作物的行数`
        （`CONVENTIONS.md` §3：每条行占一个行距宽的条带）。

            area = row_spacing_m × n_rows_of_crop × row_length_m × n_bands

        实测踩过的坑：曾把公式写成 `row_spacing × row_length × n_rows × n_bands`
        而 `row_spacing = band_width/(m+n)` —— 那等于把**整个带宽**也算进去，
        间作（带宽 2.4 m、行距 0.4 m）会**多算 2.4 倍**。
        校验：两作物面积之和应恰等于计算域面积 `n_bands × band_width × row_length`
        （见 `scripts/verify_t07_monoculture.py` 的 B1 判据）。

    Args:
        crop: 作物类型。
        layout: `StripLayout`。
        row_length_m: 沿行向的建模长度 [m]。

    Returns:
        地面面积 [m²]。

    Raises:
        ValueError: 未知作物类型，或该作物在本布局中不存在。
    """
    if crop == CROP_MAIZE:
        n_rows = layout.m
    elif crop == CROP_SOY:
        n_rows = layout.n
    else:
        raise ValueError(f"未知作物类型：{crop!r}")

    if n_rows <= 0:
        raise ValueError(
            f"作物 {crop!r} 在本布局中不存在（m={layout.m}, n={layout.n}），无地面面积"
        )

    return layout.row_spacing_m * n_rows * row_length_m * layout.n_bands


def absorbed_energy_by_crop(
    result: BandResult,
    layout,
    row_length_m: float,
    duration_h: float = EQUIVALENT_SUNSHINE_HOURS,
) -> dict[str, tuple[float, float]]:
    """按作物汇总吸收辐射能量（**地面面积**口径）。

    Args:
        result: `radiation.run_par_radiation` 的输出。
        layout: `StripLayout`，用于计算各作物的地面占地面积。
        row_length_m: 沿行向的建模长度 [m]。
        duration_h: 等效时长 [h]，用于把瞬时通量折算为日累计能量。

    Returns:
        `{作物: (平均吸收通量密度 [W/m²], 吸收能量 [MJ/m²])}`，均相对地面面积。

    Raises:
        ValueError: `duration_h` 非正。
    """
    if duration_h <= 0.0:
        raise ValueError(
            f"等效时长必须为正：duration_h={duration_h}。"
            "若要表达瞬时结果，请直接使用 radiation.BandResult，勿做日累计折算。"
        )

    out: dict[str, tuple[float, float]] = {}
    for crop, agg in result.by_crop().items():
        # ⚠️ 跳过"本布局中不存在"的作物：`BandResult.by_crop()` 恒返回两种作物键，
        #    但单作场景（T-07）下某作物的面积为 0 且无任何层 —— 那不是有效作物。
        n_rows = layout.m if crop == CROP_MAIZE else (layout.n if crop == CROP_SOY else 0)
        if n_rows <= 0 or agg["area_m2"] <= 0.0:
            continue
        ground_m2 = crop_ground_area_m2(crop, layout, row_length_m)
        if ground_m2 <= 0.0:
            out[crop] = (0.0, 0.0)
            continue
        # 相对**地面面积**的平均吸收通量密度 [W/m²]
        flux = agg["absorbed_power_w"] / ground_m2
        out[crop] = (flux, to_ground_area_mj_m2(flux, duration_h))
    return out


def compute_biomass(
    result: BandResult,
    layout,
    row_length_m: float,
    duration_h: float = EQUIVALENT_SUNSHINE_HOURS,
) -> BiomassResult:
    """吸收辐射 → 干物质 → 产量（RUE 法，逐作物）。

    Args:
        result: `radiation.run_par_radiation` 的输出。
        layout: `StripLayout`，用于计算各作物的地面占地面积。
        row_length_m: 沿行向的建模长度 [m]。
        duration_h: 等效日照时长 [h]。默认值为原型近似，
            见 `EQUIVALENT_SUNSHINE_HOURS` 与 `DESIGN.md` 附录 A。

    Returns:
        `BiomassResult`，按结果中实际存在的作物分组。

    Raises:
        ValueError: 时长非正，或结果中不含任何作物。

    Note:
        **容忍缺失作物**：单作基准（T-07）场景只有一种作物，
        故本函数按 `energy` 中实际存在的作物遍历，而不强制要求两种作物齐备。
    """
    energy = absorbed_energy_by_crop(result, layout, row_length_m, duration_h)
    if not energy:
        raise ValueError("辐射结果中不含任何作物，无法换算干物质")

    crops: dict[str, CropBiomass] = {}
    for crop, (flux_w_m2, energy_mj_m2) in energy.items():
        rue = rue_for_crop(crop)
        hi = hi_for_crop(crop)

        dry_matter = rue * energy_mj_m2          # g DM/m²
        if not math.isfinite(dry_matter):
            raise ValueError(f"{crop} 干物质计算结果非有限值：{dry_matter}")

        crops[crop] = CropBiomass(
            crop=crop,
            absorbed_flux_w_m2=flux_w_m2,
            absorbed_energy_mj_m2=energy_mj_m2,
            rue_g_dm_per_mj=rue,
            hi=hi,
            dry_matter_g_m2=dry_matter,
            yield_g_m2=dry_matter * hi,
            ground_area_m2=crop_ground_area_m2(crop, layout, row_length_m),
        )

    return BiomassResult(duration_h=duration_h, crops=crops)
