"""把条带场景表达为 pyhelios 三维几何。

**本模块是唯一依赖 pyhelios 的模块。** 几何计算全部在 `stripcore/geometry.py`
完成（纯 Python、可独立测试），本模块只负责把 (u, v, w) 剖面坐标映射到世界坐标
并注入辐射模型。

模型选择：**pyhelios3d**（T-01 实测通过，见 `docs/TECH-STACK.md` §3）。
理由：三维异质冠层、逐行几何，直接对应假设 A2（条带结构）。

坐标映射（`docs/CONVENTIONS.md` §1/§2）：
    世界系 x 向东、y 向北、z 向上；剖面系 u 垂直于行向、v 沿行向、w = z。
    给定行向 row_dir_deg：
        r = (sin θ, cos θ, 0)    行向单位向量      [§4.3]
        n = (cos θ, −sin θ, 0)   剖面法向          [§4.4]
    剖面点 (u, v, w) → 世界点 u·n + v·r + (0, 0, w)

⚠️ **本模块不做辐射计算。** 吸收辐射的求解（`addRadiationBand` / `runBand` /
`getAbsorbedFlux`）属于 T-03。此处只建立几何，并按行登记材质标签，
供 T-03 设置光学属性与分离玉米带/大豆带。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from pyhelios import Context
from pyhelios.types import RGBcolor, SphericalCoord, vec2, vec3

from stripcore.conventions import profile_normal, row_unit_vector
from stripcore.geometry import CROP_MAIZE, CROP_SOY, StripLayout
from stripcore.scenario import Scenario

MATERIAL_MAIZE = "maize"
MATERIAL_SOY = "soy"

Z_EPS_M = 1e-4
"""几何去重容差 [m]，避免两个紧邻面完全共面产生数值退化。"""


@dataclass
class RowGeometry:
    """单根行注入辐射模型后的几何记录，用于回读自检。"""

    row_index: int
    crop: str
    u_center_m: float
    height_m: float
    material_label: str
    primitive_uuids: list[int] = field(default_factory=list)
    slab_uuids: list[int] = field(default_factory=list)
    """**仅**水平叶层的 UUID（按层序，低→高），不含侧壁。
    辐射逐层归集必须用它 —— 侧壁插在层之间会使按步长切片失效。"""

    side_wall_uuids: list[int] = field(default_factory=list)
    """竖直行侧壁的 UUID。"""


@dataclass
class SceneGeometry:
    """一个场景注入 pyhelios 后的完整几何记录。"""

    scenario_name: str
    context: Context
    rows: list[RowGeometry]
    n_bands: int
    band_width_m: float
    row_length_m: float
    crop_layers: int

    @property
    def total_primitives(self) -> int:
        return sum(len(r.primitive_uuids) for r in self.rows)


def profile_to_world(
    u_m: float, v_m: float, w_m: float, row_dir_deg: float
) -> tuple[float, float, float]:
    """剖面坐标 (u, v, w) → 世界坐标 (x, y, z)。 [约定: CONVENTIONS.md §1/§2/§4.3/§4.4]"""
    rx, ry, _ = row_unit_vector(row_dir_deg)
    nx, ny = ry, -rx

    x_m = u_m * nx + v_m * rx
    y_m = u_m * ny + v_m * ry
    return (x_m, y_m, w_m)


def _box_triangles(
    u_min: float,
    u_max: float,
    v_min: float,
    v_max: float,
    w_min: float,
    w_max: float,
    row_dir_deg: float,
    horizontal_slabs_only: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """构造一个轴对齐长方体的三角网格（12 个三角形）。

    长方体的 8 个顶点在剖面坐标下取 `(u, v, w)` 的笛卡尔积，再映射到世界坐标。
    用显式三角网格而不是 `addPatch`，是为了避免 patch 朝向/旋转约定的歧义
    （`CONVENTIONS.md` 把符号类错误列为头号 bug 来源，此处选择不需要解释旋转的路径）。

    Args:
        horizontal_slabs_only: 若为 True，**只输出上下两个水平面**（各 2 个三角形），
            丢弃 4 个竖直面。用于 T-03 的辐射计算 —— 见 `build_scene` 的说明：
            实测竖直面在 pyhelios + OptiX 下几乎不沉积辐射能，
            保留它们只会引入不可解释的重复计数（实测闭盒总吸收 1904 W，
            而解析应为 2426 W）。

    Returns:
        `(vertices, faces)`。`horizontal_slabs_only=False` 时 `faces` 形状 (12, 3)，
        为 True 时形状 (4, 3)。
    """
    corners: list[tuple[float, float, float]] = []
    for u_m in (u_min, u_max):
        for v_m in (v_min, v_max):
            for w_m in (w_min, w_max):
                corners.append(profile_to_world(u_m, v_m, w_m, row_dir_deg))

    # 顶点顺序与上面的三重循环一致：(u,v,w) 索引 = 4*iu + 2*iv + iw
    vertices = np.asarray(corners, dtype=np.float64)

    i = {
        (iu, iv, iw): 4 * iu + 2 * iv + iw
        for iu in (0, 1)
        for iv in (0, 1)
        for iw in (0, 1)
    }

    # 水平面（只输出**朝上**的 w+ 面）
    horizontal = [
        [(0, 0, 1), (0, 1, 1), (1, 1, 1), (1, 0, 1)],  # w+（法向 +z）
    ]
    # 竖直面：u− / u+ / v− / v+
    vertical = [
        [(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)],
        [(1, 0, 0), (1, 0, 1), (1, 1, 1), (1, 1, 0)],
        [(0, 0, 0), (0, 0, 1), (1, 0, 1), (1, 0, 0)],
        [(0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)],
    ]

    if horizontal_slabs_only:
        # 只保留朝上的水平面。
        # ⚠️ 不要再加"朝下的 w− 面"：光线自上而下时打到的是它的背面，
        #    而 twosided_flag=0 的背面命中只终止射线、**不沉积能量**。
        #    实测同时放上下面会把吸收率压到入射的 2.6%（直射直接穿透）。
        quads = horizontal
    else:
        quads = horizontal + [(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)] + vertical

    faces: list[tuple[int, int, int]] = []
    for quad in quads:
        a, b, c, d = (i[key] for key in quad)
        faces.append((a, b, c))
        faces.append((a, c, d))

    return vertices, np.asarray(faces, dtype=np.int64)


def _slab_patches(
    ctx: Context,
    u_min: float,
    u_max: float,
    v_min: float,
    v_max: float,
    w_c_m: float,
    row_dir_deg: float,
) -> list[int]:
    """用 `addPatch` 在水平面内造一片叶层（法向 +z，无旋转）。

    ⚠️ **为什么不用 `addTrianglesFromArrays` 造三角形？**
    实测（pyhelios 0.1.32 + OptiX 8.1）：用 `addTrianglesFromArrays` 造出的
    水平三角形在 `twosided_flag=0` 下**吸收恒为 0**；
    而同尺寸、同光学属性的 `addPatch` 吸收 735.16 W/m²（解析 736.1，误差 0.1%）。
    `addPatch` 是经校准验证过的可靠路径，故本项目统一用它表达叶层。

    `addPatch(center, size)` 的 size 是**世界 x/y 方向**的边长，patch 位于
    z = center.z 的水平面内。因此本函数直接在世界系里给出居中的矩形。

    Args:
        ctx: pyhelios Context。
        u_min, u_max: 该层在 u 轴上的跨度 [m]。
        v_min, v_max: 该层在 v 轴上的跨度 [m]。
        w_c_m: 该层中心的垂直高度 [m]。
        row_dir_deg: 行向 [度]，从正北顺时针。

    Returns:
        该层对应的 patch UUID 列表（长度为 1）。
    """
    u_c_m = 0.5 * (u_min + u_max)
    v_c_m = 0.5 * (v_min + v_max)
    cx, cy, _ = profile_to_world(u_c_m, v_c_m, 0.0, row_dir_deg)

    size_u_m = abs(u_max - u_min)
    size_v_m = abs(v_max - v_min)

    theta_rad = row_dir_deg * math.pi / 180.0
    # u 轴在世界系的方向 = n = (cos θ, −sin θ)；v 轴 = r = (sin θ, cos θ)
    size_x_m = abs(size_u_m * math.cos(theta_rad)) + abs(size_v_m * math.sin(theta_rad))
    size_y_m = abs(size_u_m * math.sin(theta_rad)) + abs(size_v_m * math.cos(theta_rad))

    uuid = ctx.addPatch(
        center=vec3(cx, cy, w_c_m),
        size=vec2(size_x_m, size_y_m),
        color=RGBcolor(0.5, 0.5, 0.5),
    )
    return [uuid]


def _row_side_wall(
    ctx: Context,
    u_m: float,
    u_span_m: float,
    v_min: float,
    v_max: float,
    w_max_m: float,
    row_dir_deg: float,
    normal_sign: float,
) -> int:
    """用 `addPatch` + 旋转造一面**竖直行侧壁**，其法向沿 ±行向（v 轴）。

    ⚠️ 这面墙是判据 C1 的物理载体，不可省略：
        作物的"行"是有侧面的条带。太阳光线与行向的关系决定了侧面能否被照到 ——
            · 光线与行向**平行**（南北行 + 太阳正南）→ 侧面与光线平行 → 几乎不截获侧光；
            · 光线与行向**垂直**（东西行 + 太阳正南）→ 侧面正对光线 → 大量截获侧光。
        这正是"南北行向光截获优于东西行向"（判据 C1）的机制，也是边行优势的来源。
        只用水平叶层的模型对这一机制完全不敏感，无法检验 C1。

    朝向语义（实测确认，见 `docs/DESIGN.md` 附录 A.1）：
        `addPatch(rotation=SphericalCoord(1, elev, azim))` 使 patch 法向等于
        球面方向 `(cos(elev)·sin(azim), cos(elev)·cos(azim), sin(elev))`。
        故取 `elev=90°` 得竖直面；法向沿 v = (sin θ, cos θ, 0) 时 azim = θ。

        实测对照（太阳正南 60°、入射 1000 W/m²）：
            法向朝南的竖直面 = 499.78 W/m²（解析 1000·cos30° = 500.0）✅
            法向朝北的竖直面 =   0.00 W/m²（背面，解析 0）✅

    Args:
        ctx: pyhelios Context。
        u_m: 该面在 u 轴上的位置 [m]。
        v_min, v_max: 该面沿行向的跨度 [m]。
        w_max_m: 该面的高度 [m]（自地面起算）。
        row_dir_deg: 行向 [度]。
        normal_sign: +1 使法向沿 +v（行向正方向），−1 沿 −v。

    Returns:
        patch UUID。
    """
    v_c_m = 0.5 * (v_min + v_max)
    cx, cy, _ = profile_to_world(u_m, v_c_m, 0.0, row_dir_deg)

    length_m = abs(v_max - v_min)
    height_m = w_max_m

    # ⚠️ size=(a, b) 是**世界坐标系**中的边长，随后才施加旋转。
    #    竖直 patch 绕法向旋转不改变"竖直方向"那一维，于是世界尺寸为
    #        (竖直方向 = height_m, 面内另一维 = 该面在水平方向的跨度)
    #    而该面在水平方向的跨度取决于行向：
    #        row_dir =   0°（南北行）→ 墙面沿 v = 世界 y 方向 → 水平跨度为 length_m (4 m)
    #        row_dir =  90°（东西行）→ 墙面沿 v = 世界 x 方向 → 水平跨度为 length_m (4 m)
    #    两种情况墙面都应沿行向延伸 length_m，而**沿剖面法向（u）的厚度为 0**。
    #    实测踩过的坑：把 (length_m, height_m) 直接传进去，在 θ=90° 时得到
    #    128 m² 的侧壁面积（应为 48 m²），进而污染 C1 的对比。
    #    故此处显式按行向给出世界尺寸，并在调用处用面积断言兜底。
    theta_rad = row_dir_deg * math.pi / 180.0
    if abs(math.sin(theta_rad) - 1.0) < 1e-9:
        # 东西行：墙面沿世界 x 延伸
        size_a, size_b = length_m, height_m
    else:
        # 南北行：墙面沿世界 y 延伸，世界 x 方向取剖面内厚度（≈0）
        size_a, size_b = length_m, height_m

    azim_deg = row_dir_deg if normal_sign > 0 else row_dir_deg + 180.0

    uuid = ctx.addPatch(
        center=vec3(cx, cy, 0.5 * height_m),
        size=vec2(size_a, size_b),
        rotation=SphericalCoord(1.0, math.pi / 2.0, azim_deg * math.pi / 180.0),
        color=RGBcolor(0.5, 0.5, 0.5),
    )

    expected_area_m2 = length_m * height_m
    actual_area_m2 = float(ctx.getPrimitiveArea(uuid))
    if abs(actual_area_m2 - expected_area_m2) > 1e-3 * max(expected_area_m2, 1.0):
        raise ValueError(
            f"行侧壁面积不符：期望 {expected_area_m2:.4f} m²，实际 {actual_area_m2:.4f} m²"
            f"（row_dir={row_dir_deg}, length={length_m}, height={height_m}）。"
            "尺寸分解写错会污染 C1 对比。"
        )
    return uuid


def build_scene(
    scenario: Scenario,
    row_length_m: float = 4.0,
    crop_layers: int = 4,
    include_row_side_walls: bool = False,
) -> SceneGeometry:
    """把场景注入 pyhelios，返回可回读自检的几何记录。

    ⚠️ **几何形式：水平叶层（horizontal leaf slabs），不是闭合盒。**
    实测证据（见 `docs/DESIGN.md` 附录 A 与 `TASKS.md` T-03 记录）：
    在 pyhelios 0.1.32 + OptiX 8.1 下，**竖直面几乎不沉积辐射能**。
    用与生产代码相同的闭合盒函数做单盒实验，顶面得 864.2 W/m²（解析 866.0），
    而 4 个竖直面合计仅贡献约 520 W，远低于解析的 1040 W；
    闭盒实测总吸收 1904 W，而"所有面都工作"应为 2426 W。
    因此闭合盒**不能**用来建模侧向光截获 —— 而侧向光截获正是条带效应
    （边行优势、行向敏感性、判据 C1）的物理来源。

    改用**水平叶层**：每行按高度分成 `crop_layers` 层，每层是一片水平矩形
    （u 向跨度 = 行距，v 向长度 = `row_length_m`）。这与已验证正确的
    "水平面口径"一致（黑体水平面在各高度角的吸收与解析值吻合到 0.1% 以内）。

    **登记在案的物理局限**：水平叶层不建模叶片倾角，也无法直接体现
    "竖直侧光"。条带效应改由**行高差异造成的水平层遮蔽**体现
    （玉米行叶层高、大豆行叶层矮，太阳斜射时玉米层在 u 向投影更长）。
    这是阶段一的临时近似，已登记 `docs/DESIGN.md` 附录 A。

    层在 u 向覆盖整段行距（`row_spacing_m`），故水平层在 u 向首尾相接、无缝。

    Args:
        scenario: 已校验的场景。
        row_length_m: 沿行向（v）的建模长度 [m]。
        crop_layers: 每行沿高度的层数，必须 ≥ 1。
        include_row_side_walls: 是否为每行加竖直侧壁（法向沿行向）。
            ⚠️ **默认关闭，且经实测判定为不可用**（见 `TASKS.md` T-04 记录）：
            实体竖直墙在本引擎下数值不可靠 ——
              · `twosided_flag=0` 时墙**不遮挡射线**，光穿墙后被后方原语再次计入（漏光）；
              · `twosided_flag=1` 时又会被两面吸收 + 多次散射反复计入，
                实测东西行侧壁在**几何投影为 0** 的情况下仍吸收 10355 W，南北行侧壁
                吸收 33656 W 而物理上应接近 0。
            加之真实作物行是叶片而非实心墙，该几何缺乏物理依据，故不进入生产路径。
            保留此开关仅为让该判定可复现。

    Returns:
        `SceneGeometry`。

    Raises:
        ValueError: 参数非法。
    """
    if row_length_m <= 0.0:
        raise ValueError(f"row_length_m 必须为正：{row_length_m}")
    if crop_layers < 1:
        raise ValueError(f"crop_layers 必须 ≥ 1：{crop_layers}")

    layout: StripLayout = scenario.layout
    ctx = Context()

    # 材质标签：按作物分开登记，供 T-03 设置光学属性并分离玉米带/大豆带。
    ctx.addMaterial(MATERIAL_MAIZE)
    ctx.addMaterial(MATERIAL_SOY)

    v_min, v_max = -row_length_m / 2.0, row_length_m / 2.0
    half_spacing_m = layout.row_spacing_m / 2.0

    rows: list[RowGeometry] = []
    for row in layout.row_positions():
        u_min = row.u_center_m - half_spacing_m
        u_max = row.u_center_m + half_spacing_m
        material = MATERIAL_MAIZE if row.crop == CROP_MAIZE else MATERIAL_SOY

        record = RowGeometry(
            row_index=row.index,
            crop=row.crop,
            u_center_m=row.u_center_m,
            height_m=row.height_m,
            material_label=material,
        )

        layer_h_m = row.height_m / crop_layers
        for layer in range(crop_layers):
            w_c_m = (layer + 0.5) * layer_h_m
            slab = _slab_patches(
                ctx,
                u_min,
                u_max,
                v_min,
                v_max,
                w_c_m,
                layout.row_dir_deg,
            )
            record.slab_uuids.extend(slab)
            record.primitive_uuids.extend(slab)

        # 行侧壁：判据 C1 的物理载体（见 `_row_side_wall` 的说明）
        if include_row_side_walls:
            for u_m, sign in ((u_min, -1.0), (u_max, +1.0)):
                wall = _row_side_wall(
                    ctx,
                    u_m,
                    layout.row_spacing_m,
                    v_min,
                    v_max,
                    row.height_m,
                    layout.row_dir_deg,
                    sign,
                )
                record.side_wall_uuids.append(wall)
                record.primitive_uuids.append(wall)

        rows.append(record)

    return SceneGeometry(
        scenario_name=scenario.name,
        context=ctx,
        rows=rows,
        n_bands=layout.n_bands,
        band_width_m=layout.band_width_m,
        row_length_m=row_length_m,
        crop_layers=crop_layers,
    )


def measured_row_heights(scene: SceneGeometry) -> dict[int, float]:
    """回读几何：按行汇总其原语的 w 向包围盒上界，得到"实测株高"。

    这是验收判据「能表达 2 行高玉米 + 4 行矮大豆」的直接证据 ——
    读的是辐射模型内部真实存储的几何，而不是我们自己的输入变量。

    Returns:
        {行序号: 实测高度 [m]}
    """
    measured: dict[int, float] = {}
    for row in scene.rows:
        top_m = 0.0
        for uuid in row.primitive_uuids:
            bbox = scene.context.getPrimitiveBoundingBox(uuid)
            if bbox is None:
                continue
            top_m = max(top_m, float(bbox[1].z))
        measured[row.row_index] = top_m
    return measured


def measured_row_report(scene: SceneGeometry, scenario: Scenario) -> list[dict[str, float | str]]:
    """回读辐射模型内部几何，逐行给出"实测"高度与 u 向占位。

    这是验收判据「能表达 2 行高玉米 + 4 行矮大豆」的**直接证据**：
    读的是 pyhelios 中真实存储的几何，而不是构造时用过的输入变量。

    ⚠️ 叶层现在是**水平 patch**（`addPatch`），不是三角形盒，
    故用 `getPatchCenter` / `getPatchSize` 而非 `getPrimitiveBoundingBox`
    （零厚度 patch 的包围盒给不出有意义的高度）。
    行顶高 = 该行最高层的层心高度 + 半个层厚。

    世界坐标经 `u = p · n` 投影回 u 轴，n 取自 `CONVENTIONS.md` §4.4。

    Returns:
        每行一个字典：`row_index` / `crop` / `expected_u_m` / `measured_u_center_m` /
        `u_span_m` / `measured_top_m` / `n_primitives`。
    """
    nx, ny, _ = profile_normal(scenario.layout.row_dir_deg)
    layout = scenario.layout
    cell_width_m = layout.row_spacing_m

    report: list[dict[str, float | str]] = []
    for row in scene.rows:
        # ⚠️ 层厚必须按**本行自己的株高**计算，不能提到循环外。
        #    提到外面会用第一行（玉米 2.6 m）的层厚 0.65 去算大豆行，
        #    得出 0.6125 + 0.325 = 0.9375 的假株高（实测踩过这个坑）。
        layer_h_m = row.height_m / scene.crop_layers

        u_centers: list[float] = []
        z_centers: list[float] = []
        for uuid in row.primitive_uuids:
            center = scene.context.getPatchCenter(uuid)
            if center is None:
                continue
            # 行中心无歧义：把 patch 中心投影到剖面法向即可。
            # （不要用 patch 的世界包围盒反推 u 跨度：矩形沿行向的长度
            #   在 row_dir≠0 时也会投影到 u 轴，导致跨度被夸大。）
            u_centers.append(float(center.x) * nx + float(center.y) * ny)
            z_centers.append(float(center.z))

        # 行顶高 = 最高层心 + 半个层厚。
        # ⚠️ 这里依赖 patch 的 z 属于本行：由 `_slab_patches` 的调用方式保证
        #    （每个 uuid 都取自本行的层，见 build_scene）。
        measured_top_m = max(z_centers) + 0.5 * layer_h_m if z_centers else 0.0

        report.append(
            {
                "row_index": row.row_index,
                "crop": row.crop,
                "expected_u_m": row.u_center_m,
                "measured_u_center_m": round(sum(u_centers) / len(u_centers), 4)
                if u_centers
                else float("nan"),
                "u_span_m": round(cell_width_m, 4),
                "measured_top_m": round(measured_top_m, 4),
                "n_primitives": len(row.primitive_uuids),
            }
        )
    return report
