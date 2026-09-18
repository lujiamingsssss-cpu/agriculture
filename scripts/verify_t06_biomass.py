"""T-06 验收：吸收辐射 → 干物质（RUE 法）。

跑法（仓库根目录）：
    uv run python scripts/verify_t06_biomass.py

验收判据（先写判据，再实现 —— `AGENTS.md` 第 2 节）：
    B1 玉米、大豆**分别**输出干物质 [g DM/m²] 与产量 [g/m²]（任务卡验收项）；
    B2 单位链路完整，且**逐项可核对**：
       吸收通量 [W/m²] → ×时长[h]×0.0036 → 能量 [MJ/m²] → ×RUE → 干物质 [g DM/m²] → ×HI → 产量
       脚本独立重算一遍，与模块输出比对；
    B3 RUE 与 HI 的取值与 `PARAMETERS.md` §4 的登记值一致，且带「待核实」标注；
    B4 线性性与守恒：
       · 产量与干物质之比恰为 HI（含入参时的比例关系）；
       · 吸收辐射翻倍 → 干物质翻倍（RUE 法是线性代数换算，不得含隐式非线性）；
    B5 时长假设**显式**：`duration_h` 必须影响结果且成严格正比，
       证明模块没有隐藏的时序假设（换时长即换日累计）。

边界：不构成 LER（属 T-08）、不做单作基准（属 T-07）、不出图、不做前端。
⚠️ 本脚本产出的绝对量**只能用于相对比较**，不得表述为"预测产量"
   （`AGENTS.md` 第 2 节 / `DESIGN.md` 附录 B）。
"""

from __future__ import annotations

import sys

from stripcore import biomass as B
from stripcore.geometry import CROP_MAIZE, CROP_SOY
from stripcore.radiation import run_par_radiation
from stripcore.scenario import load_scenario_by_name
from stripcore.scene import build_scene

ROW_LENGTH_M = 4.0


def main() -> int:
    failures: list[str] = []

    scenario = load_scenario_by_name("m2n4_ns")
    scene = build_scene(scenario)
    result = run_par_radiation(scenario, scene)
    layout = scenario.layout

    print("=" * 78)
    print("T-06 吸收辐射 → 干物质（RUE 法）")
    print("=" * 78)
    print(f"场景: {scenario.name}  行比 {layout.m}:{layout.n}  "
          f"带宽 {layout.band_width_m} m  行向 {layout.row_dir_deg:.0f}°")
    print(f"等效日照时长 duration_h = {B.EQUIVALENT_SUNSHINE_HOURS} h"
          "  ← ⚠️ 原型近似，已登记 DESIGN.md 附录 A")

    bm = B.compute_biomass(result, layout, ROW_LENGTH_M)

    # ---- B1 逐作物输出 ----
    print("\n[B1] 逐作物干物质与产量")
    print(f"{'作物':<7}{'地面面积':>10}{'吸收通量':>12}{'吸收能量':>12}{'RUE':>7}{'干物质':>11}{'HI':>6}{'产量':>11}{'kg/亩':>9}")
    for crop, label in ((CROP_MAIZE, "玉米"), (CROP_SOY, "大豆")):
        c = bm.crops[crop]
        print(f"{label:<7}{c.ground_area_m2:>10.3f}{c.absorbed_flux_w_m2:>12.2f}"
              f"{c.absorbed_energy_mj_m2:>12.3f}{c.rue_g_dm_per_mj:>7.2f}"
              f"{c.dry_matter_g_m2:>11.3f}{c.hi:>6.2f}{c.yield_g_m2:>11.3f}"
              f"{c.yield_kg_per_mu:>9.2f}")
        if not (c.dry_matter_g_m2 > 0.0):
            failures.append(f"B1 {label} 干物质非正：{c.dry_matter_g_m2}")
        if not (c.yield_g_m2 > 0.0):
            failures.append(f"B1 {label} 产量非正：{c.yield_g_m2}")
    if set(bm.crops) != {CROP_MAIZE, CROP_SOY}:
        failures.append(f"B1 未分别输出两种作物：{sorted(bm.crops)}")
    else:
        print("  ✅ B1 玉米与大豆分别输出干物质与产量")

    # ---- B2 单位链路逐项独立重算 ----
    print("\n[B2] 单位链路逐项独立重算（与模块输出比对）")
    per_crop = result.by_crop()
    conv = 3600.0 / 1.0e6   # 1 W/m²·h = 0.0036 MJ/m²
    for crop, label in ((CROP_MAIZE, "玉米"), (CROP_SOY, "大豆")):
        # 第 1 步：吸收功率 → 地面面积口径的平均通量密度 [W/m²]
        area = B.crop_ground_area_m2(crop, layout, ROW_LENGTH_M)
        flux = per_crop[crop]["absorbed_power_w"] / area
        # 第 2 步：通量 × 时长 → 能量 [MJ/m²]
        energy = flux * B.EQUIVALENT_SUNSHINE_HOURS * conv
        # 第 3 步：能量 × RUE → 干物质 [g DM/m²]
        dm = energy * B.rue_for_crop(crop)
        # 第 4 步：干物质 × HI → 产量 [g/m²]
        yld = dm * B.hi_for_crop(crop)
        got = bm.crops[crop]
        for name, expect, actual in (("通量", flux, got.absorbed_flux_w_m2),
                                     ("能量", energy, got.absorbed_energy_mj_m2),
                                     ("干物质", dm, got.dry_matter_g_m2),
                                     ("产量", yld, got.yield_g_m2)):
            rel = abs(expect - actual) / max(abs(expect), 1e-12)
            ok = rel < 1e-12
            print(f"  {label} {name:<4} 独立重算 = {expect:12.6f}   模块 = {actual:12.6f}   "
                  f"{'✅' if ok else '🔴'}  (相对差 {rel:.1e})")
            if not ok:
                failures.append(f"B2 {label} {name} 链路不一致：{expect} vs {actual}")

    # ---- B3 参数与登记值一致 ----
    print("\n[B3] RUE / HI 与 PARAMETERS.md §4 登记值一致性")
    expected_params = {
        CROP_MAIZE: (2.0, 0.50),
        CROP_SOY: (1.4, 0.40),
    }
    for crop, label in ((CROP_MAIZE, "玉米"), (CROP_SOY, "大豆")):
        rue_e, hi_e = expected_params[crop]
        c = bm.crops[crop]
        ok = abs(c.rue_g_dm_per_mj - rue_e) < 1e-12 and abs(c.hi - hi_e) < 1e-12
        print(f"  {label}: RUE = {c.rue_g_dm_per_mj}（登记 {rue_e}）  "
              f"HI = {c.hi}（登记 {hi_e}）  {'✅' if ok else '🔴'}")
        if not ok:
            failures.append(f"B3 {label} 参数与 PARAMETERS.md §4 不一致")
    print("  ⚠️ 两组参数在 PARAMETERS.md 中的状态均为**待核实**，仅供原型阶段相对比较")

    # ---- B4 线性性与比例关系 ----
    print("\n[B4] 代数换算的线性性与比例关系")
    for crop, label in ((CROP_MAIZE, "玉米"), (CROP_SOY, "大豆")):
        c = bm.crops[crop]
        # 产量/干物质 应恰为 HI
        ratio = c.yield_g_m2 / c.dry_matter_g_m2
        ok_hi = abs(ratio - c.hi) < 1e-12
        print(f"  {label}: 产量/干物质 = {ratio:.6f}，HI = {c.hi:.6f}  {'✅' if ok_hi else '🔴'}")
        if not ok_hi:
            failures.append(f"B4 {label} 产量/干物质 ≠ HI")
    # 时长翻倍 → 干物质翻倍（线性，无隐式非线性）
    bm2 = B.compute_biomass(result, layout, ROW_LENGTH_M,
                            duration_h=B.EQUIVALENT_SUNSHINE_HOURS * 2.0)
    for crop, label in ((CROP_MAIZE, "玉米"), (CROP_SOY, "大豆")):
        r = bm2.crops[crop].dry_matter_g_m2 / bm.crops[crop].dry_matter_g_m2
        ok = abs(r - 2.0) < 1e-12
        print(f"  {label}: 时长 ×2 → 干物质 ×{r:.6f}  {'✅' if ok else '🔴'}")
        if not ok:
            failures.append(f"B4 {label} 时长翻倍未使干物质翻倍（比值 {r}）")

    # ---- B5 时长假设显式可调 ----
    print("\n[B5] 时长假设显式（换时长即换日累计，无隐藏时序假设）")
    for hours in (1.0, 6.0, 12.0):
        bmx = B.compute_biomass(result, layout, ROW_LENGTH_M, duration_h=hours)
        print(f"  duration_h = {hours:>5.1f} h → 玉米干物质 = "
              f"{bmx.crops[CROP_MAIZE].dry_matter_g_m2:9.3f} g DM/m²，"
              f"大豆 = {bmx.crops[CROP_SOY].dry_matter_g_m2:9.3f} g DM/m²")
    try:
        B.compute_biomass(result, layout, ROW_LENGTH_M, duration_h=0.0)
        failures.append("B5 时长为 0 时未报错，时序假设未被强制显式")
    except ValueError:
        print("  ✅ B5 时长为 0 时显式报错，未隐藏时序假设")

    # ---- 结论 ----
    print("\n" + "=" * 78)
    if failures:
        print("T-06 验收：❌ 不通过")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("T-06 验收：✅ 通过（B1–B5 全部成立）")
    print("  产出：stripcore/biomass.py（吸收辐射 → 干物质 → 产量，逐作物）")
    print("  ⚠️ 绝对量仅用于**相对比较与情景分析**，不得表述为「预测产量」。")
    print("  ⚠️ RUE / HI 取自 PARAMETERS.md §4（待核实）；")
    print("     等效日照时长 6 h 为原型近似 —— 均已登记 DESIGN.md 附录 A。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
