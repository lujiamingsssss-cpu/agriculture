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

from dataclasses import dataclass, field

import numpy as np
from pyhelios import Context

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
) -> tuple[np.ndarray, np.ndarray]:
    """构造一个轴对齐长方体的三角网格（12 个三角形）。

    长方体的 8 个顶点在剖面坐标下取 `(u, v, w)` 的笛卡尔积，再映射到世界坐标。
    用显式三角网格而不是 `addPatch`，是为了避免 patch 朝向/旋转约定的歧义
    （`CONVENTIONS.md` 把符号类错误列为头号 bug 来源，此处选择不需要解释旋转的路径）。

    Returns:
        `(vertices, faces)`；`vertices` 形状 (8, 3)，`faces` 形状 (12, 3)。
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

    faces: list[tuple[int, int, int]] = []
    # 6 个面，每面拆 2 个三角形
    quads = [
        # u- 面
        [(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)],
        # u+ 面
        [(1, 0, 0), (1, 0, 1), (1, 1, 1), (1, 1, 0)],
        # v- 面
        [(0, 0, 0), (0, 0, 1), (1, 0, 1), (1, 0, 0)],
        # v+ 面
        [(0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)],
        # w- 面
        [(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)],
        # w+ 面
        [(0, 0, 1), (0, 1, 1), (1, 1, 1), (1, 0, 1)],
    ]
    for quad in quads:
        a, b, c, d = (i[key] for key in quad)
        faces.append((a, b, c))
        faces.append((a, c, d))

    return vertices, np.asarray(faces, dtype=np.int64)


def build_scene(scenario: Scenario, row_length_m: float = 4.0, crop_layers: int = 4) -> SceneGeometry:
    """把场景注入 pyhelios，返回可回读自检的几何记录。

    每行被表达为 `crop_layers` 个沿高度堆叠的长方体薄层。层的 **u 向厚度 = 行距**，
    v 向长度 = `row_length_m`，w 向厚度 = 株高 / `crop_layers`。
    这样玉米行是"高而窄"的柱体、大豆行是"矮而窄"的柱体，
    与 `CONVENTIONS.md` §3 的行位一一对应。

    Args:
        scenario: 已校验的场景。
        row_length_m: 沿行向（v）的建模长度 [m]。假设 H3 认为 v 方向均匀，
            此长度只影响几何规模，不影响剖面内结论。
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
            # 层之间留出 Z_EPS_M 的缝，避免共面退化
            w_lo = layer * layer_h_m + (Z_EPS_M if layer > 0 else 0.0)
            w_hi = (layer + 1) * layer_h_m
            if w_hi <= w_lo:
                continue

            vertices, faces = _box_triangles(
                u_min, u_max, v_min, v_max, w_lo, w_hi, layout.row_dir_deg
            )
            colors = np.tile(
                np.array([[0.5, 0.5, 0.5]], dtype=np.float64), (vertices.shape[0], 1)
            )
            uuids = ctx.addTrianglesFromArrays(vertices, faces, colors)
            record.primitive_uuids.extend(uuids)

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
    读的是 pyhelios 中真实存储的几何包围盒，而不是构造时用过的输入变量。

    世界包围盒的两角经 `u = p · n` 投影回 u 轴，n 取自 `CONVENTIONS.md` §4.4。

    Returns:
        每行一个字典：`row_index` / `crop` / `expected_u_m` / `measured_u_span_m` /
        `measured_top_m` / `n_primitives`。
    """
    nx, ny, _ = profile_normal(scenario.layout.row_dir_deg)
    report: list[dict[str, float | str]] = []
    for row in scene.rows:
        u_vals: list[float] = []
        top_m = 0.0
        for uuid in row.primitive_uuids:
            bbox = scene.context.getPrimitiveBoundingBox(uuid)
            if bbox is None:
                continue
            top_m = max(top_m, float(bbox[1].z))
            for corner in (bbox[0], bbox[1]):
                u_vals.append(float(corner.x) * nx + float(corner.y) * ny)

        report.append(
            {
                "row_index": row.row_index,
                "crop": row.crop,
                "expected_u_m": row.u_center_m,
                "measured_u_span_m": (
                    f"[{min(u_vals):.3f}, {max(u_vals):.3f}]" if u_vals else "[]"
                ),
                "measured_top_m": round(top_m, 4),
                "n_primitives": len(row.primitive_uuids),
            }
        )
    return report
