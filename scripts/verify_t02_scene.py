"""T-02 验收脚本：确认场景"能表达 2 行高玉米 + 4 行矮大豆"。

跑法（仓库根目录）：
    uv run python scripts/verify_t02_scene.py

本脚本只做**几何表达**的验证，不做辐射计算（那是 T-03）。

验收判据（先写判据，再实现 —— `AGENTS.md` 第 2 节）：
    V1 一个带内玉米行数 = m = 2、大豆行数 = n = 4；
    V2 从 pyhelios 回读的实测高度：玉米行 ≈ 2.6 m，大豆行 ≈ 0.7 m，且玉米严格高于大豆；
    V3 回读的行 u 占位与 `CONVENTIONS.md` §3 的规定一致（含第 2 个带的平移）；
    V4 剖面内光线方向是单位向量，且垂直分量 = sin(elev)。

任一条不成立 → T-02 不通过。
"""

from __future__ import annotations

import sys

from stripcore.conventions import profile_ray_direction
from stripcore.geometry import CROP_MAIZE, CROP_SOY
from stripcore.scenario import (
    load_scenario_by_name,
    scene_summary,
    verify_ray_matches_conventions,
)
from stripcore.scene import build_scene, measured_row_report

TOL_M = 1e-6


def main() -> int:
    scenario = load_scenario_by_name("m2n4_ns")
    layout = scenario.layout

    print("=" * 68)
    print(scene_summary(scenario))
    print("=" * 68)

    failures: list[str] = []

    # ---- V1 行比 --------------------------------------------------------
    n_maize, n_soy = layout.crop_counts_per_band()
    print(f"\n[V1] 单带行比：玉米 {n_maize} 行 / 大豆 {n_soy} 行（期望 {layout.m} / {layout.n}）")
    if (n_maize, n_soy) != (layout.m, layout.n):
        failures.append(f"V1 行比不符：得到 {n_maize}:{n_soy}，期望 {layout.m}:{layout.n}")

    # ---- 注入 pyhelios 并回读 -------------------------------------------
    scene = build_scene(scenario)
    report = measured_row_report(scene, scenario)
    print(f"\n[pyhelios] 注入完成：行数 {len(scene.rows)}，原语数 {scene.total_primitives}")
    print(f"{'行':>3} {'作物':<6} {'期望u':>8} {'实测u中心':>9}  {'实测顶高':>8}")
    for item in report:
        print(
            f"{item['row_index']:>3} {item['crop']:<6} {item['expected_u_m']:>8.3f} "
            f"{item['measured_u_center_m']:>9.3f}  {item['measured_top_m']:>8.3f}"
        )

    # ---- V2 实测高度 ----------------------------------------------------
    print("\n[V2] 实测株高（从 pyhelios 包围盒回读）")
    maize_tops = [i["measured_top_m"] for i in report if i["crop"] == CROP_MAIZE]
    soy_tops = [i["measured_top_m"] for i in report if i["crop"] == CROP_SOY]
    print(f"  玉米行顶高：{maize_tops}")
    print(f"  大豆行顶高：{soy_tops}")

    if len(maize_tops) != 2 * layout.n_bands:
        failures.append(f"V2 玉米行数 {len(maize_tops)}，期望 {2 * layout.n_bands}")
    if len(soy_tops) != 4 * layout.n_bands:
        failures.append(f"V2 大豆行数 {len(soy_tops)}，期望 {4 * layout.n_bands}")
    if any(abs(t - layout.h_maize_m) > 1e-3 for t in maize_tops):
        failures.append(f"V2 玉米实测株高偏离 {layout.h_maize_m} m：{maize_tops}")
    if any(abs(t - layout.h_soy_m) > 1e-3 for t in soy_tops):
        failures.append(f"V2 大豆实测株高偏离 {layout.h_soy_m} m：{soy_tops}")
    if max(maize_tops, default=0) <= max(soy_tops, default=0):
        failures.append("V2 玉米未严格高于大豆，未构成条带异质冠层")

    # ---- V3 行位 --------------------------------------------------------
    print("\n[V3] 行中心 u 与 CONVENTIONS §3 对齐")
    for row, item in zip(scene.rows, report, strict=True):
        got = item["measured_u_center_m"]
        if abs(float(got) - row.u_center_m) > 1e-3:
            failures.append(
                f"V3 行{row.row_index} u 中心不符：实测 {got}，期望 {row.u_center_m}"
            )
    print(f"  已逐行核对 {len(scene.rows)} 行行中心（容差 1e-3 m）")

    # ---- V4 光线几何 ----------------------------------------------------
    print("\n[V4] 剖面内光线自检（对照 CONVENTIONS §4.5/§4.6）")
    try:
        verify_ray_matches_conventions(scenario)
    except AssertionError as exc:
        failures.append(f"V4 {exc}")
    dir_u, dir_w = profile_ray_direction(
        scenario.sun.elev_deg, scenario.sun.azim_deg, layout.row_dir_deg
    )
    ray = scenario.ray_geometry()
    print(f"  归一化方向 (dir_u, dir_w) = ({dir_u:.4f}, {dir_w:.4f})")
    print(f"  等效天顶角 zenith_eff = {ray['zenith_eff_deg']:.2f}°")
    print("  解读：本场景为南北行(0°)+ 太阳正南(180°)，行向与太阳方位平行，")
    print("        perpComp = s·n = 0 → 剖面内光线垂直入射、行间受光均匀（§4.5 第 1 行）。")
    print("  注：判据 C1 要比较的是南北 vs 东西的总光截获，需要真实辐射计算，")
    print("      属于 T-03/T-04；本脚本对 C1 不作任何结论。")

    # ---- 结论 -----------------------------------------------------------
    print("\n" + "=" * 68)
    if failures:
        print("T-02 验收：❌ 不通过")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("T-02 验收：✅ 通过（V1–V4 全部成立）")
    print("  场景已能表达：%d 行高玉米 (%.1f m) + %d 行矮大豆 (%.1f m)" % (
        len(maize_tops), layout.h_maize_m, len(soy_tops), layout.h_soy_m
    ))
    print("  ⚠️ 参数取自 PARAMETERS.md 默认值（状态：待核实），已登记 DESIGN.md 附录 A。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
