"""批量跑多种带型并出对比表。对应 `docs/TASKS.md` T-09。

**用途**：给出不同行比在**同一模型、同一参数集**下的相对比较。
这是本项目的主用途（`DESIGN.md` §4.4：做**相对比较**，不做绝对产量预测）。

⚠️ **绝对量纪律**：表中的 g/m²、kg/亩 只用于**相对比较与情景分析**，
    不得表述为"预测产量"（`AGENTS.md` 第 2 节 / `DESIGN.md` 附录 B）。

**纪律**：每种带型走**同一条**链路
    `radiation.run_par_radiation` → `biomass.compute_biomass` → `ler.compute_ler`，
不做任何按带型的分支特判。单作基准复用 T-07 的结果（同一模型、同一参数集）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from stripcore import biomass as B
from stripcore.geometry import CROP_MAIZE, CROP_SOY
from stripcore.ler import LERResult, compute_ler
from stripcore.radiation import run_par_radiation
from stripcore.scenario import load_scenario_by_name
from stripcore.scene import build_scene

ROW_LENGTH_M = 4.0
"""沿行向的建模长度 [m]，与各验收脚本一致。"""

DEFAULT_BASELINE_SCENARIOS: dict[str, str] = {
    CROP_MAIZE: "mono_maize",
    CROP_SOY: "mono_soy",
}
"""单作基准场景名（T-07 产出）。"""


@dataclass
class StripTypeRow:
    """对比表中的一行（一个带型）。"""

    scenario_name: str
    m: int
    n: int
    row_spacing_m: float
    n_bands: int
    canopy_area_m2: float
    # 逐作物的关键量
    absorbed_flux_w_m2: dict[str, float] = field(default_factory=dict)
    absorbed_energy_mj_m2: dict[str, float] = field(default_factory=dict)
    dry_matter_g_dm_m2: dict[str, float] = field(default_factory=dict)
    yield_g_m2: dict[str, float] = field(default_factory=dict)
    yield_ratio: dict[str, float] = field(default_factory=dict)
    area_share: dict[str, float] = field(default_factory=dict)
    ler: float = 0.0
    """标准土地当量比（口径 A，面积份额加权）。"""

    ler_ratio_sum: float = 0.0
    """附注口径（口径 B，未加权比值之和）。"""


def run_strip_type(
    scenario_name: str,
    solo: dict[str, B.BiomassResult],
    row_length_m: float = ROW_LENGTH_M,
) -> StripTypeRow:
    """跑一个带型，返回对比表的一行。

    Args:
        scenario_name: 场景名（对应 `scenarios/<name>.json`）。
        solo: `{作物: 单作基准结果}`，由 T-07 的场景算出。
        row_length_m: 沿行向的建模长度 [m]。

    Returns:
        `StripTypeRow`。

    Raises:
        ValueError: 场景缺少某作物，或单作基准缺失。
    """
    scenario = load_scenario_by_name(scenario_name)
    layout = scenario.layout
    scene = build_scene(scenario)
    result = run_par_radiation(scenario, scene)
    bm = B.compute_biomass(result, layout, row_length_m)

    ler_res: LERResult = compute_ler(layout, solo, bm, row_length_m)

    row = StripTypeRow(
        scenario_name=scenario_name,
        m=layout.m,
        n=layout.n,
        row_spacing_m=layout.row_spacing_m,
        n_bands=layout.n_bands,
        canopy_area_m2=result.total_canopy_area_m2,
        ler=ler_res.ler_area_weighted,
        ler_ratio_sum=ler_res.ler_ratio_sum,
    )
    for crop in (CROP_MAIZE, CROP_SOY):
        c = bm.crops[crop]
        row.absorbed_flux_w_m2[crop] = c.absorbed_flux_w_m2
        row.absorbed_energy_mj_m2[crop] = c.absorbed_energy_mj_m2
        row.dry_matter_g_dm_m2[crop] = c.dry_matter_g_m2
        row.yield_g_m2[crop] = c.yield_g_m2
        row.yield_ratio[crop] = ler_res.crops[crop].ratio
        row.area_share[crop] = ler_res.crops[crop].area_share
    return row


def load_baselines(
    baseline_scenarios: dict[str, str] | None = None,
    row_length_m: float = ROW_LENGTH_M,
) -> dict[str, B.BiomassResult]:
    """载入并计算 T-07 的单作基准（复用，不重写算法）。

    Args:
        baseline_scenarios: `{作物: 场景名}`；None 用默认。
        row_length_m: 沿行向的建模长度 [m]。

    Returns:
        `{作物: 单作 BiomassResult}`。
    """
    mapping = baseline_scenarios or DEFAULT_BASELINE_SCENARIOS
    solo: dict[str, B.BiomassResult] = {}
    for crop, name in mapping.items():
        scenario = load_scenario_by_name(name)
        scene = build_scene(scenario)
        result = run_par_radiation(scenario, scene)
        solo[crop] = B.compute_biomass(result, scenario.layout, row_length_m)
    return solo


def run_batch(
    scenario_names: list[str],
    row_length_m: float = ROW_LENGTH_M,
    baseline_scenarios: dict[str, str] | None = None,
) -> tuple[list[StripTypeRow], dict[str, B.BiomassResult]]:
    """批量跑多个带型。

    Args:
        scenario_names: 场景名列表。
        row_length_m: 沿行向的建模长度 [m]。
        baseline_scenarios: 单作基准场景映射；None 用默认。

    Returns:
        `(各行结果, 单作基准)`。
    """
    solo = load_baselines(baseline_scenarios, row_length_m)
    rows = [run_strip_type(name, solo, row_length_m) for name in scenario_names]
    return rows, solo
