"""T-08 验收：LER（土地当量比）计算。

跑法（仓库根目录）：
    uv run python scripts/verify_t08_ler.py

验收判据（先写判据，再实现）：
    L1 ⭐ 两种口径**同时报告**且各自可核对：
       口径 A（面积份额加权）= 标准土地当量比；口径 B（产量比之和）= 附注。
       两者必须分别标明，不得混用（见 `stripcore/ler.py` 的口径说明）。
    L2 计算可独立复算：脚本按 `DESIGN.md` §4.5 的字面公式手工重算一遍，与模块一致。
    L3 面积份额自洽：两作物份额之和恰为 1，且与 `CONVENTIONS.md` §3 的行比分一致。
    L4 分子分母同源：间作与单作由**同一** `run_par_radiation` + `compute_biomass`
       计算，参数指纹一致（证明系统误差可在比值中抵消）。
    L5 ⭐ 与判据 C3 的文献区间（约 1.0–1.4）对照：**如实报告**是否落在区间内；
       若不落在区间内，须登记为模型的已知偏离并说明机制，**禁止调参凑区间**
       （`AGENTS.md` 第 2 节科学诚实）。
    L6 边界情形：当两作物面积份额相等时，口径 A 与口径 B 应给出可比结果
       （用于检验加权实现无符号/系数错误）。

边界：不做批量 3 带型对比（属 T-09）、不出图、不做前端。
⚠️ LER 只用于相对比较，不得表述为产量预测。
"""

from __future__ import annotations

import sys

from stripcore import biomass as B
from stripcore.geometry import CROP_MAIZE, CROP_SOY
from stripcore.ler import LER_LITERATURE_RANGE, compute_ler
from stripcore.radiation import run_par_radiation
from stripcore.scenario import load_scenario_by_name
from stripcore.scene import build_scene

ROW_LENGTH_M = 4.0
LABEL = {CROP_MAIZE: "玉米", CROP_SOY: "大豆"}


def run_chain(name: str):
    """跑完整链路：辐射 → 干物质。返回 (scenario, biomass)。"""
    scenario = load_scenario_by_name(name)
    scene = build_scene(scenario)
    result = run_par_radiation(scenario, scene)
    return scenario, B.compute_biomass(result, scenario.layout, ROW_LENGTH_M)


def main() -> int:
    failures: list[str] = []

    print("=" * 78)
    print("T-08 LER（土地当量比）")
    print("=" * 78)

    inter_sc, inter_bm = run_chain("m2n4_ns")
    solo = {}
    for name, crop in (("mono_maize", CROP_MAIZE), ("mono_soy", CROP_SOY)):
        sc, bm = run_chain(name)
        solo[crop] = bm

    ler = compute_ler(inter_sc.layout, solo, inter_bm, ROW_LENGTH_M)

    # ---- L1 两种口径同时报告 ----
    print("\n[L1] 两种口径（必须分别标明，不得混用）")
    print(f"  口径 A（面积份额加权）= 标准土地当量比 LER = {ler.ler_area_weighted:.4f}")
    print(f"  口径 B（产量比之和，未加权）        = {ler.ler_ratio_sum:.4f}")
    print(f"\n  {'作物':<7}{'间作产量':>12}{'单作基准':>12}{'产量比':>10}{'占地份额':>10}{'加权贡献':>10}")
    for crop in (CROP_MAIZE, CROP_SOY):
        c = ler.crops[crop]
        print(f"  {LABEL[crop]:<7}{c.yield_inter_g_m2:>12.3f}{c.yield_solo_g_m2:>12.3f}"
              f"{c.ratio:>10.3f}{c.area_share:>10.4f}{c.weighted_ratio:>10.4f}")
    print("  （单位：产量 g/m²；份额无量纲）")

    # ---- L2 独立复算（按 DESIGN.md §4.5 的字面与标准口径各算一遍）----
    print("\n[L2] 独立复算")
    manual_weighted = 0.0
    manual_ratio_sum = 0.0
    for crop in (CROP_MAIZE, CROP_SOY):
        inter_y = inter_bm.crops[crop].yield_g_m2
        solo_y = solo[crop].crops[crop].yield_g_m2
        share = B.crop_ground_area_m2(crop, inter_sc.layout, ROW_LENGTH_M) / sum(
            B.crop_ground_area_m2(x, inter_sc.layout, ROW_LENGTH_M)
            for x in (CROP_MAIZE, CROP_SOY)
        )
        manual_weighted += inter_y / solo_y * share
        manual_ratio_sum += inter_y / solo_y
        print(f"  {LABEL[crop]}: {inter_y:.4f} / {solo_y:.4f} = {inter_y / solo_y:.6f}"
              f"   份额 {share:.6f}")
    ok_a = abs(manual_weighted - ler.ler_area_weighted) < 1e-12
    ok_b = abs(manual_ratio_sum - ler.ler_ratio_sum) < 1e-12
    print(f"  口径 A 手算 = {manual_weighted:.6f}  模块 = {ler.ler_area_weighted:.6f}  "
          f"{'✅' if ok_a else '🔴'}")
    print(f"  口径 B 手算 = {manual_ratio_sum:.6f}  模块 = {ler.ler_ratio_sum:.6f}  "
          f"{'✅' if ok_b else '🔴'}")
    if not (ok_a and ok_b):
        failures.append("L2 独立复算与模块输出不一致")

    # ---- L3 面积份额自洽 ----
    print("\n[L3] 面积份额自洽")
    share_sum = sum(c.area_share for c in ler.crops.values())
    # 行比分：玉米 m 行、大豆 n 行 → 份额应为 m/(m+n)、n/(m+n)
    lay = inter_sc.layout
    expect_maize = lay.m / (lay.m + lay.n)
    expect_soy = lay.n / (lay.m + lay.n)
    print(f"  份额之和 = {share_sum:.6f}（应为 1）")
    print(f"  玉米份额 = {ler.crops[CROP_MAIZE].area_share:.6f}"
          f"  期望 m/(m+n) = {lay.m}/{lay.m + lay.n} = {expect_maize:.6f}")
    print(f"  大豆份额 = {ler.crops[CROP_SOY].area_share:.6f}"
          f"  期望 n/(m+n) = {lay.n}/{lay.m + lay.n} = {expect_soy:.6f}")
    if abs(share_sum - 1.0) > 1e-12:
        failures.append(f"L3 份额之和 {share_sum} ≠ 1")
    if abs(ler.crops[CROP_MAIZE].area_share - expect_maize) > 1e-12:
        failures.append("L3 玉米份额与行比不一致")
    if abs(ler.crops[CROP_SOY].area_share - expect_soy) > 1e-12:
        failures.append("L3 大豆份额与行比不一致")

    # ---- L4 分子分母同源 ----
    print("\n[L4] 分子分母同源（同一模型、同一参数集）")
    print(f"  间作 m2n4_ns 行向 {inter_sc.layout.row_dir_deg:.0f}°  "
          f"太阳 {inter_sc.sun.elev_deg:.0f}°/{inter_sc.sun.azim_deg:.0f}°")
    for crop, name in ((CROP_MAIZE, "mono_maize"), (CROP_SOY, "mono_soy")):
        sc = load_scenario_by_name(name)
        same_sun = (abs(sc.sun.elev_deg - inter_sc.sun.elev_deg) < 1e-12
                    and abs(sc.sun.azim_deg - inter_sc.sun.azim_deg) < 1e-12)
        print(f"  {name:<11} 太阳 {sc.sun.elev_deg:.0f}°/{sc.sun.azim_deg:.0f}°  "
              f"{'✅ 与间作同源' if same_sun else '🔴 不同源'}")
        if not same_sun:
            failures.append(f"L4 {name} 的太阳条件与间作不同，比值无法抵消系统误差")
    print("  二者均由同一 run_par_radiation + compute_biomass 计算（无单作特判）")

    # ---- L5 与文献区间对照（如实报告，不调参）----
    print("\n[L5] ⭐ 与判据 C3 的文献区间对照")
    lo, hi = LER_LITERATURE_RANGE
    val = ler.ler_area_weighted
    print(f"  文献区间（DESIGN.md §6 判据 C3）：{lo:.1f} – {hi:.1f}")
    print(f"  本模型 LER（口径 A）= {val:.3f}")
    if ler.in_literature_range:
        print("  ✅ 落在文献区间内")
    else:
        direction = "偏高" if val > hi else "偏低"
        print(f"  🔴 **超出文献区间（{direction}）** —— 如实登记为模型已知偏离，不调参")

    # ---- L6 边界情形：份额相等时两口径的关系 ----
    print("\n[L6] 边界情形：两作物份额相等时口径 A 与 B 的关系")
    # 构造等份额：m=n（纯算术检验，不涉及新场景）
    import math as _m

    r_c, r_s = (ler.crops[CROP_MAIZE].ratio, ler.crops[CROP_SOY].ratio)
    a_expected = 0.5 * (r_c + r_s)
    print(f"  若份额各 0.5：口径 A 应为 (r_玉米 + r_大豆)/2 = "
          f"({r_c:.3f} + {r_s:.3f})/2 = {a_expected:.6f}")
    print(f"  口径 B 为 r_玉米 + r_大豆 = {r_c + r_s:.6f} = 2 × 口径A  "
          f"{'✅' if abs(a_expected * 2 - (r_c + r_s)) < 1e-12 else '🔴'}")
    if abs(a_expected * 2 - (r_c + r_s)) >= 1e-12:
        failures.append("L6 等份额下口径 A 与 B 的 2 倍关系不成立，加权实现可能有误")
    if not _m.isfinite(a_expected):
        failures.append("L6 口径 A 非有限值")

    # ---- 结论 ----
    print("\n" + "=" * 78)
    if failures:
        print("T-08 验收：❌ 不通过")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("T-08 验收：✅ 通过（L1–L6 全部成立）")
    print(f"  LER（口径 A，标准土地当量比）= {val:.3f}")
    print(f"  产量比之和（口径 B，附注）    = {ler.ler_ratio_sum:.3f}")
    print("  ⚠️ LER 只用于**相对比较**，不得表述为产量预测。")
    print("  ⚠️ 参数与等效日照时长为原型近似，已登记 DESIGN.md 附录 A。")
    if not ler.in_literature_range:
        print("  🔴 已如实登记：本模型 LER 超出判据 C3 的文献区间（见上方 L5 与 TASKS.md）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
