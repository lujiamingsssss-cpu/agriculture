"""T-04 验收：判据 C1 ⭐ —— 南北行向的光截获必须严格大于东西行向。

跑法（仓库根目录）：
    uv run python scripts/verify_t04_criterion_c1.py

判据原文（`docs/CONVENTIONS.md` §7）：
    固定其余全部参数，仅令 `row_dir_deg` 由 `0.0` 改为 `90.0`。
    **南北向（0°）的光截获量必须严格大于东西向（90°）。**
    不通过 → 停在组 A，按 `CONVENTIONS.md` §4 逐项核对，**禁止调参掩盖**。

为什么这条判据是"免费的模型自检"：
    南北行向下，太阳（正南）与行向平行 → 剖面内光线接近垂直入射 → 行间受光均匀；
    东西行向下，太阳与行向垂直 → 剖面内光线倾斜最大 → 前排遮挡后排。
    这是农学上已知的结果，因此可以直接用来验证坐标系与投影实现是否正确。

本脚本的判据：
    C1a 两场景**只差行向**：其余全部参数逐项相同（防止"调参掩盖"）；
    C1b ⭐ 南北向光截获 **严格大于** 东西向（判据本体）；
    C1c 只比较**行向**这一个变量：两场景的太阳条件、行比、带宽、株高、LAI 全同；
    C1d 效果量报告：给出相对差，供判断"严格大于"是否只是数值噪声；
    C1e 判据自检：`CONVENTIONS.md` §4 的投影必须给出
        南北等效天顶角 < 东西等效天顶角（这是 C1 的物理前提）；
        若本项不成立而 B 项成立，说明投影实现有误，结论不可信。

本脚本不出剖面图（属 T-10），不做产量 / LER（属 T-06~T-08）。
"""

from __future__ import annotations

import sys

import numpy as np

from stripcore.conventions import effective_zenith_deg
from stripcore.geometry import CROP_MAIZE, CROP_SOY
from stripcore.radiation import run_par_radiation
from stripcore.scenario import load_scenario_by_name
from stripcore.scene import build_scene

TOL_REL = 1e-9


def measure(name: str) -> dict[str, object]:
    """跑一个场景，返回用于 C1 判定的量。"""
    scenario = load_scenario_by_name(name)
    scene = build_scene(scenario)
    result = run_par_radiation(scenario, scene)
    per_crop = result.by_crop()

    return {
        "scenario": scenario,
        "result": result,
        "total_absorbed_w": result.total_absorbed_power_w,
        "maize_absorbed_w": per_crop[CROP_MAIZE]["absorbed_power_w"],
        "soy_absorbed_w": per_crop[CROP_SOY]["absorbed_power_w"],
        "ground_area_m2": result.domain_ground_area_m2,
        "canopy_area_m2": result.total_canopy_area_m2,
    }


def param_fingerprint(scenario) -> dict[str, float]:
    """除行向外全部参数的指纹，用于证明"只差行向"。"""
    lay = scenario.layout
    return {
        "m": float(lay.m),
        "n": float(lay.n),
        "band_width_m": lay.band_width_m,
        "h_maize_m": lay.h_maize_m,
        "h_soy_m": lay.h_soy_m,
        "lai_maize": lay.lai_maize,
        "lai_soy": lay.lai_soy,
        "n_bands": float(lay.n_bands),
        "sun_elev_deg": scenario.sun.elev_deg,
        "sun_azim_deg": scenario.sun.azim_deg,
    }


def main() -> int:
    ns = measure("m2n4_ns")
    ew = measure("m2n4_ew")

    sc_ns, sc_ew = ns["scenario"], ew["scenario"]
    failures: list[str] = []

    print("=" * 76)
    print("判据 C1：南北行向(0°) vs 东西行向(90°)，其余参数完全相同")
    print("=" * 76)

    print("\n[C1a] 两场景参数指纹（必须只差 row_dir_deg）")
    fp_ns, fp_ew = param_fingerprint(sc_ns), param_fingerprint(sc_ew)
    for key in fp_ns:
        same = abs(fp_ns[key] - fp_ew[key]) < 1e-12
        mark = "同" if same else "⚠️不同"
        print(f"  {key:<16} 南北={fp_ns[key]:<10.4f} 东西={fp_ew[key]:<10.4f} {mark}")
        if not same:
            failures.append(f"C1a 参数 {key} 在两场景中不同：{fp_ns[key]} vs {fp_ew[key]}")
    print(f"  row_dir_deg      南北={sc_ns.layout.row_dir_deg:<10.1f} "
          f"东西={sc_ew.layout.row_dir_deg:<10.1f} ← 唯一变量")

    # ---- C1e 物理前提自检（先于结果判定）----
    print("\n[C1e] 判据的物理前提自检（CONVENTIONS.md §4.5/§4.6）")
    z_ns = effective_zenith_deg(
        sc_ns.sun.elev_deg, sc_ns.sun.azim_deg, sc_ns.layout.row_dir_deg
    )
    z_ew = effective_zenith_deg(
        sc_ew.sun.elev_deg, sc_ew.sun.azim_deg, sc_ew.layout.row_dir_deg
    )
    print(f"  剖面内等效天顶角：南北 {z_ns:.3f}°  东西 {z_ew:.3f}°")
    print("  物理预期：南北应更接近垂直（天顶角更小）→ 行间遮挡更少")
    if not (z_ns < z_ew):
        failures.append(
            f"C1e 物理前提不成立：南北等效天顶角 {z_ns:.3f}° 未小于东西 {z_ew:.3f}°。"
            "投影实现可能有误，C1b 结论不可信"
        )

    # ---- C1b 判据本体 ----
    print("\n[C1b] ⭐ 光截获量对比")
    a_ns = float(ns["total_absorbed_w"])
    a_ew = float(ew["total_absorbed_w"])
    print(f"  冠层总吸收功率：南北 = {a_ns:12.3f} W   东西 = {a_ew:12.3f} W")
    for crop, label in ((CROP_MAIZE, "玉米"), (CROP_SOY, "大豆")):
        v_ns = float(ns[f"{'maize' if crop == CROP_MAIZE else 'soy'}_absorbed_w"])
        v_ew = float(ew[f"{'maize' if crop == CROP_MAIZE else 'soy'}_absorbed_w"])
        print(f"    {label}带：南北 = {v_ns:12.3f} W   东西 = {v_ew:12.3f} W")

    # 按计算域地面面积归一，便于跨场景比较
    g_ns = float(ns["ground_area_m2"])
    g_ew = float(ew["ground_area_m2"])
    q_ns, q_ew = a_ns / g_ns, a_ew / g_ew
    print(f"  单位地面面积吸收：南北 = {q_ns:9.4f} W/m²   东西 = {q_ew:9.4f} W/m²")

    if not (a_ns > a_ew):
        failures.append(
            f"C1b **判据 C1 失败**：南北向光截获 {a_ns:.3f} W 未严格大于东西向 {a_ew:.3f} W。"
            "按 CONVENTIONS.md §7：停在组 A，按 §4 逐项核对，禁止调参掩盖"
        )

    # ---- C1d 效果量 ----
    print("\n[C1d] 效果量")
    if a_ew > 0:
        rel = (a_ns - a_ew) / a_ew
        print(f"  南北相对东西的优势 = {rel:+.4%}")
        if 0 < rel < 1e-6:
            failures.append(
                f"C1d 优势仅 {rel:.2e}，处于数值噪声量级，不足以断言'严格大于'"
            )
    else:
        print("  东西向吸收为 0，无法计算相对差")
        failures.append("C1d 东西向吸收为 0，结果不可信")

    # ---- 结论 ----
    print("\n" + "=" * 76)
    if failures:
        print("T-04 验收：❌ 不通过")
        for f in failures:
            print(f"  - {f}")
        print("\n  ⚠️ 按 CONVENTIONS.md §7：不通过则停在组 A，")
        print("     按 §4 逐项核对坐标系与投影，**禁止通过调参掩盖**。")
        return 1

    print("T-04 验收：✅ 通过（C1a–C1e 全部成立）")
    print(f"  ⭐ 判据 C1 成立：南北向光截获 {a_ns:.1f} W > 东西向 {a_ew:.1f} W"
          f"（优势 {(a_ns - a_ew) / a_ew:+.2%}）")
    print("  这是阶段一的第一个 checkpoint，通过后 CONVENTIONS.md 不得再改。")
    print("  ⚠️ 参数与固定太阳角为原型阶段近似，已登记 DESIGN.md 附录 A。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
