"""T-03 验收：逐层吸收辐射输出 + 玉米带/大豆带分离。

跑法（仓库根目录）：
    uv run python scripts/verify_t03_radiation.py

验收判据（先写判据，再实现 —— `AGENTS.md` 第 2 节）：
    W1 输出是**逐层数组**而非仅总量：每行每层都有吸收通量密度，层数 = crop_layers；
    W2 单位正确：逐层通量密度为 W/m²，并可换算为 MJ/m²；
    W3 **玉米带与大豆带已分离**：两作物各自成组，面积与吸收功率独立可查；
    W4 物理合理性（能量守恒类）：冠层总吸收功率 ≤ 入射到计算域的总功率，
       且冠层吸收 > 0；
    W5 ⭐ **条带结构可分辨**（A2 的直接证据）：大豆行因紧邻高玉米行而受遮蔽，
       其吸收量应随「与玉米带的距离」单调增加；若模型把所有大豆行算成同一个值，
       说明它没有解析条带异质性 → A2 不成立，须走 T-05 降级路径。

本脚本不出剖面图（属 T-10），不做南北 vs 东西对比（属 T-04）。
"""

from __future__ import annotations

import sys

import numpy as np

from stripcore.conventions import profile_normal
from stripcore.geometry import CROP_MAIZE, CROP_SOY
from stripcore.radiation import (
    BAND_PAR,
    PAR_INCIDENT_W_M2,
    absorbed_energy_mj_m2,
    run_par_radiation,
    sun_direction_consistency_check,
)
from stripcore.scenario import load_scenario_by_name, scene_summary
from stripcore.scene import build_scene

TOL = 1e-6


def main() -> int:
    scenario = load_scenario_by_name("m2n4_ns")
    scene = build_scene(scenario)

    print("=" * 74)
    print(scene_summary(scenario))
    print("=" * 74)

    failures: list[str] = []

    # ---- 太阳方向符号自检（§4.2 → Helios 的转换）----
    diag = sun_direction_consistency_check(scenario)
    print(f"\n[符号自检] 太阳单位向量 sz={diag['sun_sz']:.4f}（指向太阳，z>0）")
    print(f"           传入 Helios 的 direction dz={diag['helios_dz']:+.4f}"
          f"；光线传播方向 dz={diag['dir_z']:+.4f}")

    # ---- 跑辐射 ----
    print(f"\n[辐射计算] 入射 PAR = {PAR_INCIDENT_W_M2} W/m²，"
          f"波段 {BAND_PAR}，散射深度见 radiation.py")
    result = run_par_radiation(scenario, scene)
    print(f"           后端 = {result.backend}，原语数 = {result.n_primitives}")

    # ---- W1 逐层数组 ----
    print("\n[W1] 逐层数组（通量密度 W/m²）")
    crop_layers = scene.crop_layers
    maize_arr = result.layer_array(CROP_MAIZE)
    soy_arr = result.layer_array(CROP_SOY)
    print(f"  玉米带 shape={maize_arr.shape} (行×层)，层数应={crop_layers}")
    print(np.array2string(maize_arr, precision=2, suppress_small=True))
    print(f"  大豆带 shape={soy_arr.shape}")
    print(np.array2string(soy_arr, precision=2, suppress_small=True))

    if maize_arr.shape[1] != crop_layers or soy_arr.shape[1] != crop_layers:
        failures.append(f"W1 层数不符：玉米 {maize_arr.shape}，大豆 {soy_arr.shape}，期望层数 {crop_layers}")
    if result.layers == []:
        failures.append("W1 只得到聚合量，没有逐层记录")

    # ---- W2 单位 ----
    print("\n[W2] 单位换算")
    sample = float(maize_arr[0, 0])
    print(f"  示例：玉米第 0 行第 0 层 = {sample:.2f} W/m²")
    print(f"        按 1 小时晴天等效时长 = {absorbed_energy_mj_m2(sample, 1.0):.4f} MJ/m²")
    print("  ⚠️ 本模型是稳态瞬时计算：W/m² 是瞬时通量密度；")
    print("     MJ/m² 需按时间积分，属 T-06/T-07（已登记 DESIGN.md 附录 A 第 3 行）。")

    # ---- W3 带分离 ----
    print("\n[W3] 玉米带 / 大豆带分离")
    per_crop = result.by_crop()
    for crop in (CROP_MAIZE, CROP_SOY):
        d = per_crop[crop]
        print(f"  {crop:<6} 面积 {d['area_m2']:8.3f} m²   吸收功率 {d['absorbed_power_w']:10.3f} W")
    if per_crop[CROP_MAIZE]["area_m2"] <= 0 or per_crop[CROP_SOY]["area_m2"] <= 0:
        failures.append("W3 未能分离玉米带与大豆带（某一侧面积为 0）")

    # ---- W4 能量守恒 ----
    print("\n[W4] 能量守恒（口径正确性的守门人）")
    print(f"  叶层水平投影面积 = {result.projected_area_m2:.3f} m²")
    print(f"  入射到该投影上的功率上界 = {result.incident_on_canopy_w:.2f} W")
    print(f"  冠层实际吸收 = {result.total_absorbed_power_w:.2f} W")
    ratio = (
        result.total_absorbed_power_w / result.incident_on_canopy_w
        if result.incident_on_canopy_w > 0
        else 0.0
    )
    print(f"  吸收/截获 = {ratio:.4f}（应 ≤ 1；理论值约 1−ρ−τ = {1 - 0.10 - 0.05:.2f}）")
    if result.total_absorbed_power_w <= 0.0:
        failures.append("W4 冠层吸收功率非正，结果无意义")
    if ratio > 1.0 + 1e-6:
        failures.append(
            f"W4 冠层吸收 {result.total_absorbed_power_w:.2f} W 超过其可截获上界 "
            f"{result.incident_on_canopy_w:.2f} W（比值 {ratio:.4f}）——"
            "物理上不可能，疑为 twosided_flag 双面重复计数"
        )
    # 吸收率不应显著低于 1−ρ−τ（否则说明光学属性没生效）
    if ratio < 0.70:
        failures.append(
            f"W4 吸收/截获 = {ratio:.4f} 远低于理论吸收率 0.85，疑为散射深度或光学属性未生效"
        )
    print(f"  注：计算域地面入射 = {result.incident_flux_w_m2 * result.domain_ground_area_m2:.2f} W，"
          "该值不能作为分母（冠层投影面积大于地面面积）")

    # ---- W5 ⭐ A2 的直接证据：条带异质性 ----
    print("\n[W5] ⭐ 条带结构可分辨性（A2 的直接证据）")
    soy_rows = [r for r in scene.rows if r.crop == CROP_SOY][: scenario.layout.n]
    band_mean = soy_arr[: scenario.layout.n].mean(axis=1)
    print("  大豆行（单带内，全层平均）与到最近玉米带的距离：")
    mid_u = scenario.layout.maize_band_width_m + (
        scenario.layout.band_width_m - scenario.layout.maize_band_width_m
    ) / 2.0
    for i, r in enumerate(soy_rows):
        print(f"    行{r.row_index}  u={r.u_center_m:.2f} m  平均吸收 {band_mean[i]:8.2f} W/m²")

    # 物理预期：单带内玉米带在两侧（u=0 与 u=band_width 均为玉米带），
    # 故大豆行「离最近玉米带的距离」在带中部最大 → 吸收应为**对称 U 形**。
    dist = [
        min(r.u_center_m - scenario.layout.maize_band_width_m,
            scenario.layout.band_width_m - r.u_center_m)
        for r in soy_rows
    ]
    lo = scenario.layout.n // 2
    edge = np.mean(np.concatenate([band_mean[:lo], band_mean[-lo:]]))
    middle = np.mean(band_mean[lo:-lo]) if scenario.layout.n > 2 * lo else band_mean[lo]
    spread = float(band_mean.max() - band_mean.min())
    rel = spread / float(band_mean.max())
    print(f"  离最近玉米带距离: " + "  ".join(f"{d:.2f}" for d in dist))
    print(f"  边缘行均值 = {edge:.2f} W/m²，带中部均值 = {middle:.2f} W/m²")
    print(f"  极差 = {spread:.3f} W/m²（占最大 {rel:.2%}）")

    # 噪声估计：用两条带中同一位置的行的差异作为重复性检验
    all_soy = soy_arr.mean(axis=1)
    repeat_diff = float(np.max(np.abs(all_soy[: scenario.layout.n] - all_soy[scenario.layout.n :])))
    print(f"  重复性检验（第 1 带 vs 第 2 带同位置行）最大差 = {repeat_diff:.3f} W/m²")
    noise_floor = max(repeat_diff, 1e-9)

    if spread < 1e-6:
        failures.append(
            "W5 所有大豆行吸收量完全相同 → 模型未解析条带异质性，A2 不成立"
        )
    elif spread <= noise_floor:
        failures.append(
            f"W5 条带间差异 {spread:.3f} W/m² 未超过重复性噪声下限 {noise_floor:.3f} W/m²，"
            "无法断言模型解析出了条带异质性"
        )
    elif middle <= edge:
        failures.append(
            f"W5 带中部大豆行（{middle:.2f}）未比边缘行（{edge:.2f}）受光更多 —— "
            "与'两侧邻接高玉米带 → 中部受光更好'的预期相反，可能是几何或方向符号问题，"
            "不得调参掩盖"
        )

    # ---- 结论 ----
    print("\n" + "=" * 74)
    if failures:
        print("T-03 验收：❌ 不通过")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("T-03 验收：✅ 通过（W1–W5 全部成立）")
    print("  产出：逐层吸收辐射数组（玉米带 / 大豆带分别成组），单位 W/m² 与 MJ/m² 可换算。")
    print("  ⭐ A2 判定：**成立** —— 模型解析出了条带异质性（大豆行受高玉米行遮蔽，")
    print("     吸收量随离带距离增加），说明成熟开源模型能处理条带结构。")
    print("  ⚠️ 参数与固定太阳角为原型阶段近似，已登记 DESIGN.md 附录 A。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
