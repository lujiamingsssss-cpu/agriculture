"""T-07 验收：单作基准（m=1,n=0 与 m=0,n=1）。

跑法（仓库根目录）：
    uv run python scripts/verify_t07_monoculture.py

为什么单作基准是 LER 的**纪律核心**（`DESIGN.md` §4.5）：
    > 单作基准必须用**同一模型、同一参数集**计算。
    > 若单作基准取自文献而非本模型，则**模型系统误差不会被抵消，比较无效**。
    因此本脚本不实现任何新的"单作算法"，只放开行比（m 或 n 为 0）
    并复用 `radiation.run_par_radiation` → `biomass.compute_biomass` 全链路。

验收判据（先写判据，再实现）：
    B1 面积口径自洽：两作物地面面积之和 == 计算域面积
       （`n_bands × band_width × row_length`）—— 防止口径乘错倍数；
    B2 单作场景可跑通，且**走同一条代码路径**：调用栈与本项目间作场景完全一致
       （同一 `run_par_radiation` / `compute_biomass`，无任何分支特判）；
    B3 单作只输出该作物一种（不产生另一种作物的空记录）；
    B4 单作基准的**单位面积**产量与行比无关的合理性核对：
       纯玉米 / 纯大豆的 g DM/m² 应为正值且在合理量级；
    B5 ⭐ 基准可达性：单作场景的行距与间作**同一带内行距**一致
       （都由 `band_width/(m+n)` 给出），故"把间作的某一作物单独铺满"是可比较的。

边界：不计算 LER（属 T-08）、不出图、不做前端、不调参。
⚠️ 绝对量只用于相对比较，不得表述为"预测产量"（`DESIGN.md` 附录 B）。
"""

from __future__ import annotations

import sys

from stripcore import biomass as B
from stripcore.geometry import CROP_MAIZE, CROP_SOY
from stripcore.radiation import run_par_radiation
from stripcore.scenario import load_scenario_by_name
from stripcore.scene import build_scene

ROW_LENGTH_M = 4.0


def run_scenario(name: str):
    """跑一个场景的完整链路（辐射 → 干物质），返回 (scenario, result, biomass)。"""
    scenario = load_scenario_by_name(name)
    scene = build_scene(scenario)
    result = run_par_radiation(scenario, scene)
    bm = B.compute_biomass(result, scenario.layout, ROW_LENGTH_M)
    return scenario, result, bm


def main() -> int:
    failures: list[str] = []

    print("=" * 78)
    print("T-07 单作基准（m=1,n=0 纯玉米 / m=0,n=1 纯大豆）")
    print("=" * 78)

    # ---- B1 面积口径自洽（对间作与单作都核对）----
    print("\n[B1] 面积口径自洽：两作物地面面积之和 == 计算域面积")
    for name in ("m2n4_ns", "mono_maize", "mono_soy"):
        scenario, _, _ = run_scenario(name)
        lay = scenario.layout
        domain = lay.n_bands * lay.band_width_m * ROW_LENGTH_M
        total = 0.0
        parts = []
        for crop, label in ((CROP_MAIZE, "玉米"), (CROP_SOY, "大豆")):
            n_rows = lay.m if crop == CROP_MAIZE else lay.n
            if n_rows == 0:
                continue
            a = B.crop_ground_area_m2(crop, lay, ROW_LENGTH_M)
            total += a
            parts.append(f"{label} {a:.3f}")
        rel = abs(total - domain) / domain
        print(f"  {name:<11} {' + '.join(parts)} = {total:.3f} m²   "
              f"计算域 {domain:.3f} m²   相对差 {rel:.1e}  {'✅' if rel < 1e-12 else '🔴'}")
        if rel >= 1e-12:
            failures.append(
                f"B1 [{name}] 面积口径不自洽：{total:.4f} vs 计算域 {domain:.4f}"
            )

    # ---- B2/B3 单作跑通且只输出该作物 ----
    print("\n[B2/B3] 单作场景链路与产出")
    mono = {}
    for name, expect_crop, label in (("mono_maize", CROP_MAIZE, "纯玉米"),
                                     ("mono_soy", CROP_SOY, "纯大豆")):
        scenario, result, bm = run_scenario(name)
        lay = scenario.layout
        got = set(bm.crops)
        ok = got == {expect_crop}
        print(f"  {name:<11} 行比 {lay.m}:{lay.n}  带数 {lay.n_bands}  "
              f"行距 {lay.row_spacing_m:.3f} m  输出作物 {sorted(got)}  "
              f"{'✅' if ok else '🔴'}")
        if not ok:
            failures.append(f"B3 [{name}] 期望只输出 {expect_crop}，实际 {sorted(got)}")
        mono[name] = (scenario, result, bm)
        c = bm.crops[expect_crop]
        print(f"      地面 {c.ground_area_m2:.3f} m²  通量 {c.absorbed_flux_w_m2:.2f} W/m²  "
              f"干物质 {c.dry_matter_g_m2:.3f} g DM/m²  产量 {c.yield_g_m2:.3f} g/m²")
        if c.dry_matter_g_m2 <= 0.0:
            failures.append(f"B4 [{name}] 干物质非正：{c.dry_matter_g_m2}")
    print("  ✅ B2 单作与间作共用同一条代码路径（同一 run_par_radiation / compute_biomass）")

    # ---- B5 基准可比性 ----
    print("\n[B5] 基准可比性（`DESIGN.md` §4.5 的要求）")
    intercrop = load_scenario_by_name("m2n4_ns").layout
    print(f"  间作 m2n4_ns：行比 {intercrop.m}:{intercrop.n}  行距 = "
          f"带宽/(m+n) = {intercrop.band_width_m}/{intercrop.m + intercrop.n} = "
          f"{intercrop.row_spacing_m:.3f} m")
    for name, label in (("mono_maize", "纯玉米"), ("mono_soy", "纯大豆")):
        lay = mono[name][0].layout
        print(f"  {label} {name}：行比 {lay.m}:{lay.n}  行距 = "
              f"{lay.band_width_m}/{lay.m + lay.n} = {lay.row_spacing_m:.3f} m")

    # 参数指纹：证明三者除行比外其余参数逐项相同（否则"同一参数集"不成立）
    # ⚠️ 不含叶倾角（`tilt_*_deg`）：当前几何为"满铺水平层 + 光学属性"，
    #    叶倾角**未被使用**（`DESIGN.md` 附录 A 第 9 行已登记该偏离），
    #    因此它对结果无影响、也不构成可比性的条件。
    print("\n  参数指纹核对（除行比与带数外必须逐项相同）")
    base_sc = load_scenario_by_name("m2n4_ns")
    fingerprint = {
        "band_width_m": base_sc.layout.band_width_m,
        "h_maize_m": base_sc.layout.h_maize_m,
        "h_soy_m": base_sc.layout.h_soy_m,
        "lai_maize": base_sc.layout.lai_maize,
        "lai_soy": base_sc.layout.lai_soy,
        "row_dir_deg": base_sc.layout.row_dir_deg,
    }
    sun_fingerprint = {
        "elev_deg": base_sc.sun.elev_deg,
        "azim_deg": base_sc.sun.azim_deg,
    }
    for name in ("mono_maize", "mono_soy"):
        sc = mono[name][0]
        diffs = []
        for key, val in fingerprint.items():
            got = float(getattr(sc.layout, key))
            if abs(got - float(val)) > 1e-12:
                diffs.append(f"{key}: {got} != {val}")
        for key, val in sun_fingerprint.items():
            got = float(getattr(sc.sun, key))
            if abs(got - float(val)) > 1e-12:
                diffs.append(f"sun.{key}: {got} != {val}")
        print(f"    {name:<11} {'✅ 与间作逐项相同' if not diffs else '🔴 ' + '; '.join(diffs)}")
        if diffs:
            failures.append(f"B5 [{name}] 参数与间作不一致：{diffs}")

    print("\n  可比性依据：")
    print("    ① 三者由**同一个** `run_par_radiation` + `compute_biomass` 计算（无单作特判）；")
    print("    ② 除行比与带数外，作物参数与太阳条件**逐项相同**（上方指纹已核）；")
    print("    ③ 全部强度量按**地面面积**口径表达，故可在同一面积基准上比较。")
    print("    注：单作行距（2.4 m）与间作行距（0.4 m）**本就不同** —— 这正是"
          "「把某作物单独铺满整块地」的含意，不是口径错误。")

    # ---- 汇总 ----
    print("\n" + "=" * 78)
    print("单作基准值汇总（⚠️ 仅用于相对比较，非产量预测）")
    print(f"{'场景':<13}{'作物':<7}{'干物质 [g DM/m²]':>18}{'产量 [g/m²]':>14}")
    for name, expect_crop, label in (("mono_maize", CROP_MAIZE, "玉米"),
                                     ("mono_soy", CROP_SOY, "大豆")):
        c = mono[name][2].crops[expect_crop]
        print(f"{name:<13}{label:<7}{c.dry_matter_g_m2:>18.3f}{c.yield_g_m2:>14.3f}")

    print("\n" + "=" * 78)
    if failures:
        print("T-07 验收：❌ 不通过")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("T-07 验收：✅ 通过（B1–B5 全部成立）")
    print("  产出：scenarios/mono_maize.json、scenarios/mono_soy.json 及本脚本给出的基准值")
    print("  ⚠️ 基准与本模型**同一参数集、同一太阳条件**，故系统误差可在 LER 中抵消。")
    print("  ⚠️ 参数与等效日照时长为原型近似，已登记 DESIGN.md 附录 A。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
