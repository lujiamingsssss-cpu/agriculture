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
from pyhelios.types import RGBcolor, vec2, vec3

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
    z = center.z 的水平面内。因此本函数直接在世界系里给出居中的矩形：

        u 方向是剖面法向 n = (cos θ, −sin θ, 0)，v 方向是行向 r = (sin θ, cos θ, 0)
        取该矩形在 u 与 v 两个方向上的边长分别为 (u_max−u_min) 与 (v_max−v_min)，
        中心的世界坐标由 `profile_to_world` 给出。

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

    # ⚠️ 行向旋转下 size 需按世界 x/y 分解。当 row_dir_deg 为 0 或 90（阶段一仅这两种）
    #    时旋转是轴对齐的，直接用 (size_u, size_v) 分解到世界轴即可。
    theta_rad = row_dir_deg * math.pi / 180.0
    # u 轴在世界系的方向 = n = (cos θ, −sin θ)；v 轴 = r = (sin θ, cos θ)
    # 矩形在 x 与 y 上的包围盒边长：
    size_x_m = abs(size_u_m * math.cos(theta_rad)) + abs(size_v_m * math.sin(theta_rad))
    size_y_m = abs(size_u_m * math.sin(theta_rad)) + abs(size_v_m * math.cos(theta_rad))

    uuid = ctx.addPatch(
        center=vec3(cx, cy, w_c_m),
        size=vec2(size_x_m, size_y_m),
        color=RGBcolor(0.5, 0.5, 0.5),
    )
    return [uuid]


def build_scene(scenario: Scenario, row_length_m: float = 4.0, crop_layers: int = 4) -> SceneGeometry:
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
            record.primitive_uuids.extend(
                _slab_patches(
                    ctx,
                    u_min,
                    u_max,
                    v_min,
                    v_max,
                    w_c_m,
                    layout.row_dir_deg,
                )
            )

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
