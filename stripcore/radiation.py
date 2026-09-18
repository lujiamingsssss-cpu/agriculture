"""冠层吸收辐射计算（pyhelios RadiationModel 封装）。

对应 T-03：对条带场景输出**逐层吸收辐射**，并分离玉米带 / 大豆带。

物理量与单位（`docs/CONVENTIONS.md` §5）：
    pyhelios `getAbsorbedFlux(band)` 返回**吸收辐射通量密度** [W/m²]（逐原语），
    不是功率 [W]。转成功率须乘以该原语的面积，再转成 MJ/m² 单位的地面面积口径。

    ⚠️ `docs/CONVENTIONS.md` §5 规定辐射能量内部单位为 `MJ/m²`。
    本模块内部沿用 pyhelios 的 W/m²（辐射通量密度），
    在 `to_ground_area_mj_m2()` 处统一转换为 MJ/m²，**换算集中在 `conventions.py`**。

关键 API 事实（来自 Helios 官方辐射模型文档，非猜测）：
    ① 光学属性的原语数据标签必须带波段后缀：
       `reflectivity_<band>` / `transmissivity_<band>`，默认值 0。
       **吸收率不直接设置，恒等于 1 − ρ − τ。**
    ② 若设置了 ρ/τ 却把 `setScatteringDepth` 留为默认 0，
       修改过的辐射属性会被**覆盖回默认黑体**。故必须显式设置散射深度。
    ③ `twosided_flag` 默认 1：薄片两面都吸收，而通量按**单面**面积归一化。
       因此水平薄片在垂直入射下吸收通量约为入射通量的 2 倍。
       这是 Helios 的定义（"per unit one-sided surface area"），不是 bug。
    ④ 应使用 `getAbsorbedFlux(band)`，**不要**用 `getTotalAbsorbedFlux()`：
       后者排序与 `getAllUUIDs()` 不一致（哈希序），且在注册多波段时求和。

时间单位说明：
    本模型是**稳态**辐射传输，给定入射通量后立即得到吸收通量。
    场景中的 `sun.elev_deg/azim_deg` 只决定光线方向，不含时间。
    故吸收量以**瞬时通量密度** [W/m²] 表达；若需日累计 [MJ/(m²·d)]，
    必须按时间积分多个太阳位置（属 T-06/T-07，已在 `DESIGN.md` 附录 A 第 3 行登记）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from pyhelios import Context, RadiationModel

from stripcore.conventions import profile_normal, row_unit_vector, sun_unit_vector
from stripcore.geometry import CROP_MAIZE, CROP_SOY
from stripcore.scenario import Scenario

BAND_PAR = "PAR"
"""光合有效辐射波段标签。波长范围 400–700 nm。"""

WAVELENGTH_PAR_NM: tuple[float, float] = (400.0, 700.0)

SECONDS_PER_HOUR: float = 3600.0
"""小时 → 秒。用于把瞬时通量积分成能量（T-06/T-07 使用）。"""

# ── 光学属性默认值 ──
# ⚠️ 阶段一临时近似，已登记 docs/DESIGN.md 附录 A。
# 玉米/大豆冠层的 PAR 反射率约为 0.08–0.12（绿色叶片在 PAR 波段反射率低）。
REFLECTIVITY_CANOPY_PAR: float = 0.10
"""冠层 PAR 反射率（无量纲）。[临时近似: docs/DESIGN.md 附录 A]"""

TRANSMISSIVITY_CANOPY_PAR: float = 0.05
"""冠层 PAR 透射率（无量纲）。[临时近似: docs/DESIGN.md 附录 A]"""

REFLECTIVITY_GROUND_PAR: float = 0.15
"""地面 PAR 反射率（无量纲）。[临时近似: docs/DESIGN.md 附录 A]"""

PAR_INCIDENT_W_M2: float = 1000.0
"""入射 PAR 通量密度 [W/m²]（晴天正午量级）。

⚠️ 这是**瞬时**通量密度，不是日累计。
`docs/PARAMETERS.md` §3 的 `PAR_INCIDENT` 单位为 MJ/(m²·d) 且状态「待核实」，
本值**不是**该参数，仅是稳态单时刻情景的入射条件。
[临时近似: docs/DESIGN.md 附录 A]
"""

SCATTERING_DEPTH: int = 2
"""散射迭代次数。

⚠️ 必须显式设置：若修改了 ρ/τ 却保持默认 0，Helios 会把辐射属性
**覆盖回默认黑体**（官方文档明确说明）。取 2 以计入少量多次散射，
同时控制 GPU 耗时。
"""


@dataclass
class LayerFlux:
    """单个「行 × 高度层」的吸收辐射记录。"""

    crop: str
    row_index: int
    band_index: int
    layer_index: int
    w_lo_m: float
    w_hi_m: float
    flux_density_w_m2: float
    """该层全部原语按面积加权的平均吸收通量密度 [W/m²]。"""

    area_m2: float
    """该层原语的总单面面积 [m²]。"""

    absorbed_power_w: float
    """该层吸收功率 [W] = Σ(通量密度 × 面积)。"""


@dataclass
class BandResult:
    """一次辐射计算的完整结果。"""

    band_label: str
    incident_flux_w_m2: float
    backend: str
    n_primitives: int
    layers: list[LayerFlux] = field(default_factory=list)
    total_absorbed_power_w: float = 0.0
    total_canopy_area_m2: float = 0.0
    domain_ground_area_m2: float = 0.0
    projected_area_m2: float = 0.0
    """冠层叶层的水平投影面积 [m²]（= 总单面面积 / 2）。"""

    incident_on_canopy_w: float = 0.0
    """入射到冠层水平投影面积上的功率上界 [W]。"""

    total_absorbed_all_w: float = 0.0
    """**全部原语**（冠层 + 地面）的吸收功率 [W]。用于能量守恒自检。"""

    energy_ratio_all: float = 0.0
    """`total_absorbed_all_w / (入射通量 × 计算域地面面积)`。

    ⚠️ 本值 **> 1 即为能量不守恒**（物理上不可能），说明场景设置有问题。
    正常应在 0.8~1.0 之间。见 `assert_energy_conservation`。
    """

    periodic: str | None = None
    """本次计算使用的周期边界设置（`None` 表示关闭，仅用于对照）。"""

    def by_crop(self) -> dict[str, dict[str, float]]:
        """按作物聚合吸收功率与辐照面积，用于带间对比与后续 LER 计算。"""
        out: dict[str, dict[str, float]] = {}
        for crop in (CROP_MAIZE, CROP_SOY):
            sel = [lay for lay in self.layers if lay.crop == crop]
            out[crop] = {
                "absorbed_power_w": float(sum(lay.absorbed_power_w for lay in sel)),
                "area_m2": float(sum(lay.area_m2 for lay in sel)),
            }
        return out

    def layer_array(self, crop: str | None = None) -> np.ndarray:
        """返回**逐层数组**（T-03 验收要求：不得只给总量）。

        Args:
            crop: 若给定，只返回该作物的层。

        Returns:
            形状 (n_rows, n_layers) 的吸收通量密度数组 [W/m²]，
            缺失的层以 NaN 填充。行索引为该作物内的序号。
        """
        sel = [lay for lay in self.layers if crop is None or lay.crop == crop]
        if not sel:
            return np.empty((0, 0))

        rows = sorted({lay.row_index for lay in sel})
        layers = sorted({lay.layer_index for lay in sel})
        arr = np.full((len(rows), len(layers)), np.nan, dtype=np.float64)
        row_pos = {r: i for i, r in enumerate(rows)}
        lay_pos = {l: i for i, l in enumerate(layers)}
        for lay in sel:
            arr[row_pos[lay.row_index], lay_pos[lay.layer_index]] = lay.flux_density_w_m2
        return arr


def helios_source_direction(scenario: Scenario) -> tuple[float, float, float]:
    """Helios 平行光源的 `direction` 参数（世界系，归一化，z 分量为**正**）。

    ⚠️⚠️ **符号约定，实测确认（最容易写反的一处）**：
        Helios 的 `addCollimatedRadiationSource(direction=...)` 需要的是
        **由场景指向光源的方向**（即指向太阳），z 分量**为正**。

        实测对照（elev=60°，FLUX=1000 W/m²）：
            direction = +太阳单位向量 → 水平面吸收 865.893 W/m²（解析期望 866.025）✅
            direction = −太阳单位向量 → 水平面吸收 0.000 W/m²（直射全部丢失）❌

        因此本函数**直接返回 `CONVENTIONS.md` §4.2 的 `sun_unit_vector`**，
        不做取反。此处曾把语义误解为"光的传播方向"而取反，
        导致直射被完全丢弃、遮蔽效应消失（详见 TASKS.md T-03 记录）。

    Returns:
        (sx, sy, sz)，sz > 0 表示指向太阳（在地平线以上）。
    """
    return sun_unit_vector(scenario.sun.elev_deg, scenario.sun.azim_deg)


def light_travel_direction(scenario: Scenario) -> tuple[float, float, float]:
    """光线**传播**方向（世界系，归一化，z 分量为负）：由太阳射向地面。

    这是物理语义上的"光的行进方向"，等于 `−helios_source_direction`。

    ⚠️ **不要把这个向量传给 Helios 的 `addCollimatedRadiationSource`** ——
    该 API 要的是指向光源的方向（见 `helios_source_direction`）。

    Returns:
        (dx, dy, dz)，dz < 0 表示向下传播。
    """
    sx, sy, sz = sun_unit_vector(scenario.sun.elev_deg, scenario.sun.azim_deg)
    return (-sx, -sy, -sz)


def _set_optical_properties(ctx: Context, uuids: list[int], label: str, refl: float, trans: float) -> None:
    """给原语设置带波段后缀的光学属性。

    标签必须是 `reflectivity_<band>` / `transmissivity_<band>`
    （Helios 官方文档规定的命名）。吸收率由 1−ρ−τ 隐式决定。
    """
    ctx.setPrimitiveDataFloat(uuids, f"reflectivity_{label}", refl)
    ctx.setPrimitiveDataFloat(uuids, f"transmissivity_{label}", trans)


def _domain_footprint(
    layout, row_length_m: float
) -> tuple[tuple[float, float], tuple[float, float]]:
    """计算域在**世界系**的水平和范围 `((x_min, x_max), (y_min, y_max))`。

    计算域在剖面坐标下是 `u ∈ [0, n_bands·band_width_m]`、`v ∈ [−L/2, +L/2]`
    （`CONVENTIONS.md` §2/§3）。u 轴的世界方向为剖面法向 `n = (cos θ, −sin θ)`，
    v 轴为行向 `r = (sin θ, cos θ)`，故世界的轴对齐包围盒为：

        x 半跨度 = |dom_u·n_x| / 2 + |L·r_x| / 2
        y 半跨度 = |dom_u·n_y| / 2 + |L·r_y| / 2
        x 中心   = dom_u·n_x / 2,  y 中心 = dom_u·n_y / 2
    """
    nx, ny, _ = profile_normal(layout.row_dir_deg)
    rx, ry, _ = row_unit_vector(layout.row_dir_deg)
    dom_u = layout.n_bands * layout.band_width_m

    cx = 0.5 * dom_u * nx
    cy = 0.5 * dom_u * ny
    half_x = 0.5 * (abs(dom_u * nx) + abs(row_length_m * rx))
    half_y = 0.5 * (abs(dom_u * ny) + abs(row_length_m * ry))
    return (cx - half_x, cx + half_x), (cy - half_y, cy + half_y)


def run_par_radiation(
    scenario: Scenario,
    scene,
    incident_flux_w_m2: float = PAR_INCIDENT_W_M2,
    direct_rays: int = 5000,
    diffuse_rays: int = 10000,
    scattering_depth: int = SCATTERING_DEPTH,
    periodic: str | None = "xy",
) -> BandResult:
    """对已注入几何的场景跑 PAR 波段，返回逐层吸收辐射。

    ⚠️ **周期边界默认开启**，且这是正确性要求而不仅是精度优化：
        不开周期边界时，计算域侧向边界处会有光线进入/被重复计入，
        实测使**冠层吸收超过入射总能量**（东西行向吸收/入射 = 1.104），
        场景不满足能量守恒，行向对比因而不可信。
        开启后两侧均为 0.865，且冠层/几何紧上界 = 0.999。
        详见 `DESIGN.md` 附录 A 第 12 行。

        为此地面 patch 也改为**精确贴合计算域包围盒**（原先取 3×带宽的正方形，
        超出计算域，与周期边界不一致）。

    Args:
        scenario: 场景（提供太阳方向与行带布局）。
        scene: `stripcore.scene.SceneGeometry`，其 `context` 已含冠层几何。
        incident_flux_w_m2: 入射 PAR 通量密度 [W/m²]（水平面）。
        direct_rays: 直射光线数（Monte-Carlo 采样量）。
        diffuse_rays: 散射光线数。
        scattering_depth: 散射迭代次数，必须 > 0 才能让 ρ/τ 生效。
        periodic: 周期边界方向：`"x"` / `"y"` / `"xy"` / `None`（关闭）。
            `None` 仅用于复现"不守恒"的对照，不应用于生产。

    Returns:
        `BandResult`，含逐层数组。
    """
    layout = scenario.layout
    ctx = scene.context

    # ---- 地面：精确贴合计算域包围盒；单面（只从上方吸收）----
    from pyhelios.types import RGBcolor, vec2, vec3

    (x_min, x_max), (y_min, y_max) = _domain_footprint(layout, scene.row_length_m)
    ground_uuid = ctx.addPatch(
        center=vec3(0.5 * (x_min + x_max), 0.5 * (y_min + y_max), 0.0),
        size=vec2(x_max - x_min, y_max - y_min),
        color=RGBcolor(0.3, 0.22, 0.12),
    )
    ctx.setPrimitiveDataUInt(ground_uuid, "twosided_flag", 0)
    _set_optical_properties(
        ctx, [ground_uuid], BAND_PAR, REFLECTIVITY_GROUND_PAR, 0.0
    )

    # ---- 冠层：水平叶层 + 竖直行侧壁 ----
    # 叶层：只有朝上的一面（`_slab_patches`），单面吸收。
    # 侧壁：法向朝外；默认**双面**（twosided=1）。
    #   ⚠️ 单面墙会漏光：Helios 的 twosided_flag=0 只禁止从背面"吸收"，
    #      并不阻断射线，故光线会穿过墙体并被后方原语再次计入（实测侧壁贡献异常偏大）。
    #      墙体在物理上应当遮挡，故取双面。
    maize_slabs: list[int] = []
    soy_slabs: list[int] = []
    walls: list[int] = []
    maize_walls: list[int] = []
    soy_walls: list[int] = []
    for row in scene.rows:
        is_maize = row.crop == CROP_MAIZE
        (maize_slabs if is_maize else soy_slabs).extend(row.slab_uuids)
        (maize_walls if is_maize else soy_walls).extend(row.side_wall_uuids)
    walls = maize_walls + soy_walls

    _set_optical_properties(
        ctx, maize_slabs, BAND_PAR, REFLECTIVITY_CANOPY_PAR, TRANSMISSIVITY_CANOPY_PAR
    )
    _set_optical_properties(
        ctx, soy_slabs, BAND_PAR, REFLECTIVITY_CANOPY_PAR, TRANSMISSIVITY_CANOPY_PAR
    )
    if maize_slabs:
        ctx.setPrimitiveDataUInt(maize_slabs, "twosided_flag", 0)
    if soy_slabs:
        ctx.setPrimitiveDataUInt(soy_slabs, "twosided_flag", 0)

    if walls:
        # ⚠️ 侧壁路径经实测判定不可用（见 `scene.build_scene` 的说明）：
        #    单面漏光、双面重复计数。保留仅为让该结论可复现。
        _set_optical_properties(
            ctx, walls, BAND_PAR, REFLECTIVITY_CANOPY_PAR, TRANSMISSIVITY_CANOPY_PAR
        )
        ctx.setPrimitiveDataUInt(walls, "twosided_flag", 0)

    sx, sy, sz = helios_source_direction(scenario)
    assert sz > 0.0, f"指向光源的方向必须在地平线以上（sz>0），得到 sz={sz}"

    with RadiationModel(ctx) as rad:
        rad.addRadiationBand(BAND_PAR, *WAVELENGTH_PAR_NM)
        # ⚠️ 必须禁用发射：emissivity 默认为 1.0，而能量守恒要求
        #    eps + tau + rho = 1。PAR 属短波，不应有热发射，
        #    否则 runBand 直接报错 "must sum to 1 to ensure energy conservation"。
        rad.disableEmission(BAND_PAR)

        source_id = rad.addCollimatedRadiationSource(direction=(sx, sy, sz))
        rad.setSourceFlux(source_id, BAND_PAR, incident_flux_w_m2)
        rad.setDirectRayCount(BAND_PAR, direct_rays)
        rad.setDiffuseRayCount(BAND_PAR, diffuse_rays)
        rad.setScatteringDepth(BAND_PAR, scattering_depth)
        if periodic is not None:
            # ⚠️ 正确性要求，不是精度优化：见函数 docstring 与 DESIGN.md 附录 A 第 12 行。
            rad.enforcePeriodicBoundary(periodic)

        rad.runBand(BAND_PAR)
        backend = rad.getBackendName()

        all_uuids = list(ctx.getAllUUIDs())
        flux = np.asarray(rad.getAbsorbedFlux(BAND_PAR), dtype=np.float64)
        areas = np.asarray(ctx.getPrimitiveArea(all_uuids), dtype=np.float64)

    flux_by_uuid = {u: float(f) for u, f in zip(all_uuids, flux, strict=True)}
    area_by_uuid = {u: float(a) for u, a in zip(all_uuids, areas, strict=True)}

    # ---- 逐层归集 ----
    layers: list[LayerFlux] = []
    if scene.rows:
        crop_layers = scene.crop_layers
        for row in scene.rows:
            layer_h_m = row.height_m / crop_layers
            for layer_index in range(crop_layers):
                # ⚠️ 必须用 `slab_uuids` 而非 `primitive_uuids[::crop_layers]`：
                #    侧壁插在层之间，按步长切片会取错原语。
                uuids = row.slab_uuids[layer_index : layer_index + 1]
                if not uuids:
                    continue
                layer_area = sum(area_by_uuid.get(u, 0.0) for u in uuids)
                layer_power = sum(
                    flux_by_uuid.get(u, 0.0) * area_by_uuid.get(u, 0.0) for u in uuids
                )
                # 面积加权平均通量密度；面积为 0 时退化为 0
                mean_flux = layer_power / layer_area if layer_area > 0.0 else 0.0
                layers.append(
                    LayerFlux(
                        crop=row.crop,
                        row_index=row.row_index,
                        band_index=0,
                        layer_index=layer_index,
                        w_lo_m=layer_index * layer_h_m,
                        w_hi_m=(layer_index + 1) * layer_h_m,
                        flux_density_w_m2=mean_flux,
                        area_m2=layer_area,
                        absorbed_power_w=layer_power,
                    )
                )

    canopy_uuids = set(maize_slabs) | set(soy_slabs) | set(walls)
    total_canopy_power = sum(
        flux_by_uuid.get(u, 0.0) * area_by_uuid.get(u, 0.0) for u in canopy_uuids
    )
    total_canopy_area = sum(area_by_uuid.get(u, 0.0) for u in canopy_uuids)

    # ---- 能量守恒自检（口径正确性的守门人）----
    # 冠层可截获功率的**几何上界** = 入射通量密度 × 冠层在光线方向的投影面积。
    #   水平叶层的投影 = 计算域地面面积（各层在 u-v 平面重叠，并集即计算域）；
    #   竖直侧壁的投影 = 侧壁总面积 × |光线单位向量 · 行向单位向量|
    #                    （东西行时墙面正对太阳 → 投影大；南北行时墙面与光线平行 → 投影 ≈ 0）。
    # ⚠️ 实测踩过的坑：早期只用地面面积作分母，未计入侧壁投影，
    #    得到"吸收 167% 于上界"的假超界。
    rx, ry, _ = row_unit_vector(scenario.layout.row_dir_deg)
    sx, sy, sz = sun_unit_vector(scenario.sun.elev_deg, scenario.sun.azim_deg)
    wall_projection_fraction = abs(rx * sx + ry * sy)

    projected_area_m2 = layout.n_bands * layout.band_width_m * scene.row_length_m
    wall_area_m2 = sum(area_by_uuid.get(u, 0.0) for u in walls)
    intercepting_area_m2 = projected_area_m2 + wall_area_m2 * wall_projection_fraction
    incident_on_canopy_w = incident_flux_w_m2 * intercepting_area_m2

    # 全部原语的吸收（含地面），用于能量守恒自检
    absorbed_all_w = sum(
        flux_by_uuid.get(u, 0.0) * area_by_uuid.get(u, 0.0) for u in all_uuids
    )

    return BandResult(
        band_label=BAND_PAR,
        incident_flux_w_m2=incident_flux_w_m2,
        backend=backend,
        n_primitives=len(all_uuids),
        layers=layers,
        total_absorbed_power_w=total_canopy_power,
        total_canopy_area_m2=total_canopy_area,
        domain_ground_area_m2=layout.n_bands * layout.band_width_m * scene.row_length_m,
        projected_area_m2=projected_area_m2,
        incident_on_canopy_w=incident_on_canopy_w,
        total_absorbed_all_w=absorbed_all_w,
        energy_ratio_all=absorbed_all_w / (incident_flux_w_m2 * projected_area_m2),
        periodic=periodic,
    )


def assert_energy_conservation(result: BandResult, tol: float = 1.02) -> None:
    """断言场景满足能量守恒：**全部原语**（冠层 + 地面）吸收 ≤ 入射总能量。

    ⚠️ 这是本模块最重要的自检。T-04 曾因漏掉它而在**不守恒的场景**中做了
    一整套行向对比，得出与物理不符的结论（东西行向吸收/入射 = 1.104 > 1）。
    该自检是最廉价的守门人：不守恒即说明场景设置有问题（典型原因是缺周期边界），
    此时任何对比结论都不可信。

    Args:
        result: `run_par_radiation` 的输出。
        tol: 容许的相对超出（默认 1.02，为 Monte-Carlo 采样留 2% 余量）。

    Raises:
        AssertionError: 吸收总量超过入射总能量的 `tol` 倍。
    """
    ratio = result.energy_ratio_all
    if ratio > tol:
        raise AssertionError(
            f"能量不守恒：全部原语吸收 {result.total_absorbed_all_w:.1f} W / "
            f"入射 {result.incident_flux_w_m2 * result.domain_ground_area_m2:.1f} W "
            f"= {ratio:.4f} > {tol}。"
            f"（periodic={result.periodic!r}）"
            "最常见原因是未启用周期边界，导致侧向边界光线重复计数。"
            "请勿在此外推任何行向对比结论 —— 先修正场景设置。"
        )


def absorbed_energy_mj_m2(flux_density_w_m2: float, duration_h: float) -> float:
    """把瞬时通量密度 [W/m²] 按给定时长积分成能量 [MJ/m²]。

    Args:
        flux_density_w_m2: 吸收通量密度 [W/m²]。
        duration_h: 持续时长 [h]。

    Returns:
        能量 [MJ/m²]。1 W/m² × 1 h = 3600 J/m² = 0.0036 MJ/m²。
    """
    return flux_density_w_m2 * duration_h * SECONDS_PER_HOUR / 1.0e6


def sun_direction_consistency_check(scenario: Scenario) -> dict[str, float]:
    """自检：太阳向量、Helios 光源方向、光线传播方向三者的一致性。

    用于防止符号写反 —— 写反会让直射完全丢失（实测吸收量为 0），
    或让南北/东西结论整体反转。

    Returns:
        含 `elev_deg` / `azim_deg` / `dir_z` 等诊断量的字典。
    """
    sx, sy, sz = sun_unit_vector(scenario.sun.elev_deg, scenario.sun.azim_deg)
    hx, hy, hz = helios_source_direction(scenario)
    tx, ty, tz = light_travel_direction(scenario)

    # Helios 光源方向 = 太阳单位向量（指向太阳，z>0）
    assert (hx, hy, hz) == (sx, sy, sz), "Helios 光源方向必须等于太阳单位向量"
    # 光线传播方向 = 其取反
    assert abs(tx + hx) < 1e-12 and abs(ty + hy) < 1e-12 and abs(tz + hz) < 1e-12, (
        "光线传播方向必须是 Helios 光源方向的取反"
    )
    assert hz > 0.0 > tz, f"必须 sz>0>dz，得到 hz={hz}, tz={tz}"
    # 由传播方向反推高度角，应与输入一致
    elev_from_dir = math.degrees(math.asin(-tz))
    assert abs(elev_from_dir - scenario.sun.elev_deg) < 1e-9, (
        f"由传播方向反推的高度角 {elev_from_dir} 与输入 {scenario.sun.elev_deg} 不一致"
    )

    return {
        "elev_deg": scenario.sun.elev_deg,
        "azim_deg": scenario.sun.azim_deg,
        "sun_sz": sz,
        "helios_dz": hz,
        "dir_z": tz,
        "elev_from_dir_deg": elev_from_dir,
    }
