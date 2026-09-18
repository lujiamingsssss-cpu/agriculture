"""剖面吸收辐射场与热力图（T-10）。

对应 `docs/DESIGN.md` §7「可视化设计」与 `docs/TASKS.md` T-10。

**铁律**（`AGENTS.md` 第 2 节 / `DESIGN.md` DR-02）：
    数据**必须**来自计算输出的逐层吸收辐射。
    禁止手工调色，禁止用渲染亮度暗示"光更多"。
    本模块只把已经算出的物理量映射到 (u, w) 网格，不引入任何新的物理假设。

**剖面网格**（`CONVENTIONS.md` §2）：
    横轴 `u`：垂直于行向的位置 [m]；纵轴 `w`：高度 [m]。
    单元格 (i, j) 的值 = 该格内所有叶层原语的吸收功率之和 / 该格的地面投影面积，
    单位 W/m²（与 `CONVENTIONS.md` §5 的辐射通量密度口径一致）。

    ⚠️ 单位说明：本图展示的是**吸收辐射通量密度**（相对地面面积），
    不是入射辐射、也不是渲染亮度。色标必须标注物理量名与单位（`DESIGN.md` §7）。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from stripcore.geometry import CROP_MAIZE, CROP_SOY
from stripcore.radiation import BandResult
from stripcore.scenario import Scenario
from stripcore.scene import SceneGeometry


@dataclass
class ProfileField:
    """剖面吸收辐射场（规则的 u × w 网格）。"""

    u_edges_m: np.ndarray
    """u 轴单元格边界 [m]，长度 = n_u + 1。"""

    w_edges_m: np.ndarray
    """w 轴（高度）单元格边界 [m]，长度 = n_w + 1。"""

    absorbed_flux_w_m2: np.ndarray
    """形状 (n_w, n_u) 的吸收通量密度 [W/m²]，行序自下而上。"""

    row_centers_m: np.ndarray
    """各行的 u 中心 [m]。"""

    row_crops: tuple[str, ...]
    """各行的作物类型，与 `row_centers_m` 对应。"""


def build_profile_field(
    scenario: Scenario,
    scene: SceneGeometry,
    result: BandResult,
) -> ProfileField:
    """把逐层吸收辐射归集成 (u, w) 规则网格。

    Args:
        scenario: 场景（提供行带布局与计算域范围）。
        scene: 注入后的几何记录（提供每层的 u 位置与所在行）。
        result: `run_par_radiation` 的输出（提供逐层吸收功率）。

    Returns:
        `ProfileField`。

    Raises:
        ValueError: 网格无有效数据。
    """
    layout = scenario.layout

    # ---- 网格边界 ----
    # u 轴按行等分（每行一个格子），覆盖 CONVENTIONS.md §3 的整个计算域
    n_u = layout.n_rows_total * layout.n_bands
    u_edges_m = np.linspace(0.0, layout.n_bands * layout.band_width_m, n_u + 1)

    # w 轴按最高作物的层厚等分
    crop_layers = scene.crop_layers
    h_max_m = max(row.height_m for row in scene.rows)
    w_edges_m = np.linspace(0.0, h_max_m, crop_layers + 1)

    du_m = u_edges_m[1] - u_edges_m[0]
    row_length_m = scene.row_length_m
    cell_area_m2 = du_m * row_length_m
    """单元格的地面投影面积：u 向宽度 × 沿行向长度。"""

    field = np.zeros((crop_layers, n_u), dtype=np.float64)

    # 逐行、逐层把吸收功率累加到对应格子
    by_row = {row.row_index: row for row in scene.rows}
    for layer in result.layers:
        row = by_row.get(layer.row_index)
        if row is None:
            continue
        i_u = int(np.searchsorted(u_edges_m, row.u_center_m, side="right") - 1)
        if not (0 <= i_u < n_u):
            continue
        if not (0 <= layer.layer_index < crop_layers):
            continue
        field[layer.layer_index, i_u] += layer.absorbed_power_w / cell_area_m2

    if not np.any(field > 0.0):
        raise ValueError("剖面场为空：未收到任何正吸收功率，请检查场景与辐射计算")

    # 各行按 u 排序，供底部标注使用（只标注第一个带，避免重复）
    first_band = [r for r in scene.rows if r.row_index < layout.n_rows_total]
    row_centers_m = np.array([r.u_center_m for r in first_band], dtype=np.float64)
    row_crops = tuple(r.crop for r in first_band)

    return ProfileField(
        u_edges_m=u_edges_m,
        w_edges_m=w_edges_m,
        absorbed_flux_w_m2=field,
        row_centers_m=row_centers_m,
        row_crops=row_crops,
    )


def _configure_chinese_font() -> str:
    """配置 matplotlib 的中文字体，返回实际选用的字体名。

    ⚠️ 演示硬需求：不配置时中文会渲染成方框（tofu），图上标注全部不可读。
    Windows 上通常有 `Microsoft YaHei` / `SimHei`；缺失时回退到英文标签
    （`render_profile_heatmap` 会据此切换文案，保证图**始终可读**）。
    """
    import matplotlib
    from matplotlib import font_manager

    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in ("Microsoft YaHei", "SimHei", "SimSun", "Noto Sans CJK SC", "Source Han Sans SC"):
        if name in available:
            matplotlib.rcParams["font.sans-serif"] = [name]
            matplotlib.rcParams["axes.unicode_minus"] = False
            return name
    return ""


def render_profile_heatmap(
    field: ProfileField,
    scenario: Scenario,
    out_path: str,
    title: str | None = None,
) -> str:
    """把剖面场渲染为热力图并写盘。

    图内含（`DESIGN.md` §7 的强制要素）：
        · 色标：标注物理量名 + 单位 + 取值范围；
        · 横轴为 u（垂直于行向的位置，m）、纵轴为 w（高度，m）；
        · 图底部标出哪几行是玉米、哪几行是大豆。

    Args:
        field: `build_profile_field` 的输出。
        scenario: 场景（用于标题与行带说明）。
        out_path: 输出图片路径。
        title: 图标题；None 表示由场景自动生成。

    Returns:
        实际写入的路径。
    """
    import matplotlib

    matplotlib.use("Agg")  # 无显示环境（脚本/CI）必须显式指定
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    font_name = _configure_chinese_font()
    cjk = bool(font_name)

    layout = scenario.layout
    data = field.absorbed_flux_w_m2
    vmax = float(np.nanmax(data))
    vmin = 0.0

    fig, ax = plt.subplots(figsize=(9.0, 4.6), dpi=140)

    mesh = ax.pcolormesh(
        field.u_edges_m,
        field.w_edges_m,
        data,
        cmap="viridis",
        vmin=vmin,
        vmax=vmax,
        shading="flat",
    )

    cbar = fig.colorbar(mesh, ax=ax, pad=0.02)
    cbar.set_label(
        "吸收辐射通量密度 [W/m²]（PAR，相对地面面积）" if cjk
        else "Absorbed PAR flux density [W/m²] (per ground area)",
        fontsize=10,
    )
    cbar.ax.tick_params(labelsize=9)

    ax.set_xlabel("u — 垂直于行向的位置 [m]" if cjk else "u — position across rows [m]", fontsize=10)
    ax.set_ylabel("w — 高度 [m]" if cjk else "w — height [m]", fontsize=10)

    if title is None:
        title = (
            f"剖面吸收辐射分布（{layout.m}:{layout.n}，带宽 {layout.band_width_m} m，"
            f"行向 {layout.row_dir_deg:.0f}°）" if cjk
            else f"Absorbed PAR profile ({layout.m}:{layout.n}, "
                 f"band {layout.band_width_m} m, row dir {layout.row_dir_deg:.0f}°)"
        )
    ax.set_title(title, fontsize=11)

    ax.set_xlim(field.u_edges_m[0], field.u_edges_m[-1])
    ax.set_ylim(0.0, field.w_edges_m[-1])
    ax.tick_params(labelsize=9)

    # ---- 图底部标注行位（让外行瞬间看懂哪几行是玉米/大豆）----
    # ⚠️ 布局：行位色条紧贴坐标轴下方，说明文字再往下；必须与 x 轴标签留开距离，
    #    否则文字互相重叠（实测踩过：footer 与 x 轴标签压在一起，两者都不可读）。
    band_width_m = layout.band_width_m
    n_bands_drawn = max(1, int(round((field.u_edges_m[-1] - field.u_edges_m[0]) / band_width_m)))
    color_map = {CROP_MAIZE: "#d9a441", CROP_SOY: "#6aa84f"}
    label_map = {CROP_MAIZE: ("玉米" if cjk else "maize"), CROP_SOY: ("大豆" if cjk else "soy")}

    h_m = field.w_edges_m[-1]
    bar_h = 0.05 * h_m
    y_bar = -0.060 * h_m             # 行位色条：紧贴坐标轴下方（数据坐标）
    # x 轴标签放在轴坐标 y=-0.20 处；色条与说明文字分别在其下方的数据坐标位置。
    # 三者必须错开，否则互相重叠（实测踩过：footer 压住 x 轴标签，两者都不可读）。
    ax.set_xlabel(
        "u — 垂直于行向的位置 [m]" if cjk else "u — position across rows [m]",
        fontsize=10,
    )
    ax.xaxis.set_label_coords(0.5, -0.30)

    for band in range(n_bands_drawn):
        for center_m, crop in zip(field.row_centers_m, field.row_crops, strict=True):
            u0 = center_m + band * band_width_m - layout.row_spacing_m / 2.0
            ax.add_patch(
                Rectangle(
                    (u0, y_bar),
                    layout.row_spacing_m,
                    bar_h,
                    facecolor=color_map[crop],
                    edgecolor="black",
                    linewidth=0.4,
                    clip_on=False,
                    zorder=5,
                )
            )
    rows_text = " / ".join(label_map[c] for c in field.row_crops)
    footer = (
        f"行位：{rows_text}（每带 {layout.m} 玉米 + {layout.n} 大豆，共 {n_bands_drawn} 个带）"
        if cjk else
        f"Rows: {rows_text} ({layout.m} maize + {layout.n} soy per band, {n_bands_drawn} bands)"
    )
    ax.text(
        field.u_edges_m[0],
        y_bar - 0.85 * bar_h,
        footer,
        transform=ax.transData,
        fontsize=9,
        va="top",
        ha="left",
        clip_on=False,
    )

    fig.subplots_adjust(bottom=0.26, left=0.075, right=1.0, top=0.92)
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return out_path
