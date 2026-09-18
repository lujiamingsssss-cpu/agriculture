"""场景配置：加载、校验、构造。

对应 T-02「构造最小条带场景」的**产出物**：一个可复现、可读的场景配置文件 + 它的加载器。

设计纪律：
    - 场景**只描述几何与输入条件**，不含任何辐射计算（那是 T-03）。
    - 参数取自 `docs/PARAMETERS.md` 的默认值时，其状态为「待核实」，
      已统一登记到 `docs/DESIGN.md` 附录 A「临时近似登记表」。
      **未登记的近似不得继续往下做**（`BASELINE.md` §3.4）。
    - 配置是数据（JSON），不是代码里的魔法数字。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from stripcore.conventions import (
    effective_zenith_deg,
    profile_normal,
    profile_ray_direction,
    sun_unit_vector,
)
from stripcore.geometry import StripLayout

SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "scenarios"


@dataclass(frozen=True)
class SunCondition:
    """固定太阳条件（T-02 的输入条件，非辐射模型输出）。

    阶段一任务卡把太阳角写死为 `60°/180°`，用于在 T-02/T-03 阶段排除
    太阳位置随时间变化的干扰（`TASKS.md` T-02）。
    """

    elev_deg: float
    """太阳高度角 [度]。"""

    azim_deg: float
    """太阳方位角 [度]，从正北顺时针。180 = 正南。 [约定: CONVENTIONS.md §4.1]"""


@dataclass(frozen=True)
class Scenario:
    """一个完整场景 = 条带布局 + 太阳条件。"""

    name: str
    layout: StripLayout
    sun: SunCondition

    def ray_geometry(self) -> dict[str, float]:
        """该场景在剖面内的光线几何（用于自检与后续 T-03 的输入）。

        Returns:
            含 `dir_u`/`dir_w`（剖面内单位光线方向）与 `zenith_eff_deg`（等效天顶角）的字典。
        """
        dir_u, dir_w = profile_ray_direction(
            self.sun.elev_deg, self.sun.azim_deg, self.layout.row_dir_deg
        )
        return {
            "dir_u": dir_u,
            "dir_w": dir_w,
            "zenith_eff_deg": effective_zenith_deg(
                self.sun.elev_deg, self.sun.azim_deg, self.layout.row_dir_deg
            ),
        }


def load_scenario(path: str | Path) -> Scenario:
    """从 JSON 文件加载场景并做完整性校验。

    Args:
        path: 场景配置文件的路径。

    Returns:
        校验通过的 `Scenario`。

    Raises:
        FileNotFoundError: 文件不存在。
        ValueError: 缺少必需字段，或几何自相矛盾。
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"场景配置文件不存在：{path}")

    raw = json.loads(path.read_text(encoding="utf-8"))

    for section in ("name", "strip", "sun"):
        if section not in raw:
            raise ValueError(f"场景配置缺少必需字段 `{section}`：{path}")

    strip = raw["strip"]
    sun = raw["sun"]

    required_strip = (
        "m",
        "n",
        "band_width_m",
        "row_dir_deg",
        "h_maize_m",
        "h_soy_m",
        "lai_maize",
        "lai_soy",
    )
    missing = [k for k in required_strip if k not in strip]
    if missing:
        raise ValueError(f"场景 `strip` 缺少字段 {missing}：{path}")

    layout = StripLayout(
        m=int(strip["m"]),
        n=int(strip["n"]),
        band_width_m=float(strip["band_width_m"]),
        row_dir_deg=float(strip["row_dir_deg"]),
        h_maize_m=float(strip["h_maize_m"]),
        h_soy_m=float(strip["h_soy_m"]),
        lai_maize=float(strip["lai_maize"]),
        lai_soy=float(strip["lai_soy"]),
        n_bands=int(strip.get("n_bands", 2)),
    )

    for key in ("elev_deg", "azim_deg"):
        if key not in sun:
            raise ValueError(f"场景 `sun` 缺少字段 `{key}`：{path}")

    sun_condition = SunCondition(
        elev_deg=float(sun["elev_deg"]),
        azim_deg=float(sun["azim_deg"]),
    )

    if not 0.0 < sun_condition.elev_deg < 90.0:
        raise ValueError(
            f"太阳高度角必须在 (0, 90) 度之间，当前 {sun_condition.elev_deg}"
            " [约定: docs/CONVENTIONS.md §4.1]"
        )

    return Scenario(name=str(raw["name"]), layout=layout, sun=sun_condition)


def load_scenario_by_name(name: str) -> Scenario:
    """按名称加载 `scenarios/<name>.json`。"""
    return load_scenario(SCENARIOS_DIR / f"{name}.json")


def scene_summary(scenario: Scenario) -> str:
    """产出人类可读的场景摘要，用于验收时肉眼确认"能表达 2 行高玉米 + 4 行矮大豆"。"""
    layout = scenario.layout
    lines: list[str] = []
    lines.append(f"场景: {scenario.name}")
    lines.append(
        f"  行比 {layout.m}:{layout.n}  带宽 {layout.band_width_m} m  "
        f"行向 {layout.row_dir_deg}°  (0=南北, 90=东西)"
    )
    lines.append(
        f"  行距 {layout.row_spacing_m:.3f} m  玉米带 {layout.maize_band_width_m:.3f} m  "
        f"域宽 {layout.domain_width_m:.3f} m ({layout.n_bands} 个带)"
    )
    lines.append(
        f"  玉米 h={layout.h_maize_m} m LAI={layout.lai_maize}  |  "
        f"大豆 h={layout.h_soy_m} m LAI={layout.lai_soy}"
    )
    lines.append(
        f"  太阳 elev={scenario.sun.elev_deg}° azim={scenario.sun.azim_deg}° (从正北顺时针)"
    )
    ray = scenario.ray_geometry()
    lines.append(
        f"  剖面内光线 (dir_u, dir_w)=({ray['dir_u']:.4f}, {ray['dir_w']:.4f})  "
        f"等效天顶角 {ray['zenith_eff_deg']:.2f}°"
    )
    lines.append("  行位（u 轴，从 0 起）:")
    for row in layout.row_positions():
        if row.index < layout.n_rows_total:
            lines.append(
                f"    [带0] 行{row.index} {row.crop:<5} u={row.u_center_m:.3f} m  h={row.height_m} m"
            )
    lines.append("  带重复周期 = band_width_m，第 2 个带整体平移 +band_width_m")
    return "\n".join(lines)


def verify_ray_matches_conventions(scenario: Scenario, tol: float = 1e-9) -> None:
    """自检：剖面内光线方向必须与 `CONVENTIONS.md` §4.5/§4.6 一致。

    校验三件事：
        R1 `(dir_u, dir_w)` 是单位向量（§4.5 明确要求 normalize）；
        R2 `tan(zenith_eff) = |dir_u| / dir_w`（§4.6，归一化不改变比值）；
        R3 `perpComp` 与手工投影 `s · n` 相等（§4.4 法向符号的一次数值回归）。

    ⚠️ 注意：`dir_w` **不等于** `sin(elev)`。归一化后它等于
    `sin(elev) / sqrt(perpComp² + sin²(elev))`，只有 `perpComp = 0` 时才等于 1。
    把两者混为一谈是符号类错误的典型形态，故在此显式校验。

    Raises:
        AssertionError: 任一自检项不成立。
    """
    ray = scenario.ray_geometry()
    dir_u, dir_w = ray["dir_u"], ray["dir_w"]

    # R1 单位向量
    norm = math.hypot(dir_u, dir_w)
    assert abs(norm - 1.0) < tol, (
        f"R1 失败：剖面内光线方向未归一化，模长={norm}"
        " [约定: docs/CONVENTIONS.md §4.5]"
    )

    # R2 等效天顶角关系
    if dir_w > 0.0:
        expected_zenith = math.atan2(abs(dir_u), dir_w) * (180.0 / math.pi)
        assert abs(expected_zenith - ray["zenith_eff_deg"]) < 1e-9, (
            "R2 失败：tan(zenith_eff) 与 |dir_u|/dir_w 不自洽："
            f"由方向得 {expected_zenith}°，由 §4.6 公式得 {ray['zenith_eff_deg']}°"
        )

    # R3 法向投影的数值回归
    sx, sy, sz = sun_unit_vector(scenario.sun.elev_deg, scenario.sun.azim_deg)
    nx, ny, _ = profile_normal(scenario.layout.row_dir_deg)
    perp_comp = sx * nx + sy * ny

    if abs(perp_comp) > tol:
        # 归一化不改变比值，故可由方向反解 perpComp 的相对大小
        assert abs(dir_u / dir_w - perp_comp / sz) < 1e-9, (
            "R3 失败：剖面内光线倾角与 s·n 的投影不一致。"
            "请核对 CONVENTIONS §4.4 的剖面法向符号（n = (r.y, −r.x, 0)）。"
        )
