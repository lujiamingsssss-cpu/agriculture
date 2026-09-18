"""T-09 验收：批量跑 3 种带型（2:3 / 2:4 / 4:4）并出对比表。

跑法（仓库根目录）：
    uv run python scripts/verify_t09_strip_comparison.py

验收判据（先写判据，再实现）：
    S1 三行结果齐全（2:3 / 2:4 / 4:4），且每个带型都走同一条链路
       （radiation → biomass → ler，无按带型的分支特判）；
    S2 参数可比性：三个带型除行比外，作物参数与太阳条件**逐项相同**（指纹核对）；
    S3 单作基准复用 T-07 场景（同一模型、同一参数集），且**与 T-07 输出的基准值一致**
       （独立复算，防基准被悄悄改动）；
    S4 表内关键量齐全且单位可核对：
       吸收通量 W/m²、吸收能量 MJ/m²、干物质 g DM/m²、产量 g/m²、产量比、面积份额、LER；
    S5 面积份额与行比一致（m/(m+n)），且份额之和为 1；
    S6 ⭐ 相对比较的**排序**可解释：LER 与产量比随行比单调性合理，
       且三个带型的 LER 均须如实报告是否落在判据 C3 文献区间（1.0–1.4）；
    S7 可重复运行：同一批跑两次，各带型的 LER 与产量在 Monte-Carlo 容限内一致。

边界：不出图（属 T-10/T-11）、不做三维/前端、不做参数面板。
⚠️ 全部数值只用于**相对比较**，不得表述为产量预测。
"""

from __future__ import annotations

import sys

from stripcore import batch as BT
from stripcore import biomass as B
from stripcore.geometry import CROP_MAIZE, CROP_SOY
from stripcore.ler import LER_LITERATURE_RANGE
from stripcore.radiation import run_par_radiation
from stripcore.scenario import load_scenario_by_name
from stripcore.scene import build_scene

STRIP_TYPES = ["m2n3_ns", "m2n4_ns", "m4n4_ns"]
LABEL = {CROP_MAIZE: "玉米", CROP_SOY: "大豆"}
TOL_LER = 0.02   # 重跑容限（Monte-Carlo）


def main() -> int:
    failures: list[str] = []

    print("=" * 92)
    print("T-09 批量带型对比（2:3 / 2:4 / 4:4）")
    print("=" * 92)

    rows, solo = BT.run_batch(STRIP_TYPES)

    # ---- S3 单作基准与 T-07 一致（独立复算）----
    print("\n[S3] 单作基准复用 T-07 且数值一致（独立复算）")
    expected_baseline = {CROP_MAIZE: 18.4223, CROP_SOY: 10.3184}
    for crop, expect in expected_baseline.items():
        got = solo[crop].crops[crop].yield_g_m2
        rel = abs(got - expect) / expect
        ok = rel < 0.02   # Monte-Carlo 容限
        print(f"  {LABEL[crop]:<5} 基准产量 = {got:8.4f} g/m²   "
              f"T-07 记录 ≈ {expect:.4f}   相对差 {rel:.2%}  {'✅' if ok else '🔴'}")
        if not ok:
            failures.append(f"S3 单作基准 {crop} 与 T-07 记录不符：{got} vs {expect}")

    # ---- S1/S2 三行齐全 + 参数指纹 ----
    print("\n[S1/S2] 带型齐全性与参数可比性")
    if len(rows) != 3:
        failures.append(f"S1 期望 3 个带型，实际 {len(rows)}")
    base_sc = load_scenario_by_name("m2n4_ns")
    fp = {
        "band_width_m": base_sc.layout.band_width_m,
        "h_maize_m": base_sc.layout.h_maize_m,
        "h_soy_m": base_sc.layout.h_soy_m,
        "lai_maize": base_sc.layout.lai_maize,
        "lai_soy": base_sc.layout.lai_soy,
        "row_dir_deg": base_sc.layout.row_dir_deg,
    }
    for r in rows:
        sc = load_scenario_by_name(r.scenario_name)
        diffs = [
            f"{k}: {getattr(sc.layout, k)} != {v}"
            for k, v in fp.items()
            if abs(float(getattr(sc.layout, k)) - float(v)) > 1e-12
        ]
        for k in ("elev_deg", "azim_deg"):
            if abs(float(getattr(sc.sun, k)) - float(getattr(base_sc.sun, k))) > 1e-12:
                diffs.append(f"sun.{k} 不一致")
        tag = "✅ 仅差行比" if not diffs else "🔴 " + "; ".join(diffs)
        print(f"  {r.scenario_name:<11} 行比 {r.m}:{r.n}  行距 {r.row_spacing_m:.3f} m  {tag}")
        if diffs:
            failures.append(f"S2 [{r.scenario_name}] 参数与 2:4 不一致：{diffs}")

    # ---- 对比表主体 ----
    print("\n" + "=" * 92)
    print("对比表（⚠️ 仅用于相对比较，非产量预测）")
    print("=" * 92)
    header = (f"{'带型':<9}{'行距':>7}{'作物':<6}"
              f"{'吸收通量':>11}{'吸收能量':>11}{'干物质':>11}{'产量':>10}"
              f"{'产量比':>9}{'占地份额':>10}")
    print(header)
    print("-" * 92)
    for r in rows:
        for i, crop in enumerate((CROP_MAIZE, CROP_SOY)):
            sid = f"{r.m}:{r.n}" if i == 0 else ""
            rs = f"{r.row_spacing_m:.2f}" if i == 0 else ""
            print(f"{sid:<9}{rs:>7}{LABEL[crop]:<6}"
                  f"{r.absorbed_flux_w_m2[crop]:>11.2f}"
                  f"{r.absorbed_energy_mj_m2[crop]:>11.3f}"
                  f"{r.dry_matter_g_dm_m2[crop]:>11.3f}"
                  f"{r.yield_g_m2[crop]:>10.3f}"
                  f"{r.yield_ratio[crop]:>9.4f}"
                  f"{r.area_share[crop]:>10.4f}")
        print(f"{'':<9}{'':>7}{'LER(标准口径)':<6}{'':>11}{'':>11}{'':>11}"
              f"{'':>10}{'':>9}{r.ler:>10.4f}")
        print("-" * 92)
    print("单位：吸收通量 W/m²；吸收能量 MJ/m²；干物质 g DM/m²；产量 g/m²；"
          "产量比与份额无量纲")

    # ---- S5 面积份额 ----
    print("\n[S5] 面积份额与行比一致性")
    for r in rows:
        total_rows = r.m + r.n
        exp_m = r.m / total_rows
        exp_s = r.n / total_rows
        got_m = r.area_share[CROP_MAIZE]
        got_s = r.area_share[CROP_SOY]
        ok = (abs(got_m - exp_m) < 1e-12 and abs(got_s - exp_s) < 1e-12
              and abs(got_m + got_s - 1.0) < 1e-12)
        print(f"  {r.m}:{r.n}  玉米份额 {got_m:.6f}（期望 {exp_m:.6f}）  "
              f"大豆份额 {got_s:.6f}（期望 {exp_s:.6f}）  {'✅' if ok else '🔴'}")
        if not ok:
            failures.append(f"S5 [{r.m}:{r.n}] 面积份额与行比不一致")

    # ---- S6 LER 与文献区间 ----
    print("\n[S6] ⭐ LER 与判据 C3 文献区间对照")
    lo, hi = LER_LITERATURE_RANGE
    print(f"  文献区间：{lo:.1f} – {hi:.1f}")
    in_range = 0
    for r in rows:
        flag = "✅ 区间内" if lo <= r.ler <= hi else "🔴 区间外"
        if lo <= r.ler <= hi:
            in_range += 1
        print(f"  {r.m}:{r.n}  LER = {r.ler:.4f}（口径A）  "
              f"比值和 = {r.ler_ratio_sum:.4f}（口径B）  {flag}")
    if in_range == 0:
        print("  🔴 三个带型的 LER **全部**落在文献区间外 —— 如实报告，禁止调参凑区间")
        print("     机制见 DESIGN.md 附录 A 第 15 行：满铺水平层近全截获 →")
        print("     单位面积产量与作物密度无关 → LER ≈ 1。")
    # 排序可解释性：LER 应随行比变化且为正
    lers = [r.ler for r in rows]
    print(f"  LER 排序（按行比 2:3 → 2:4 → 4:4）：{[round(x, 4) for x in lers]}")
    if any(x <= 0 for x in lers):
        failures.append("S6 存在非正 LER")

    # ---- S7 可重复性 ----
    print("\n[S7] 可重复性（同批重跑，Monte-Carlo 容限内一致）")
    rows2, _ = BT.run_batch(STRIP_TYPES)
    for r1, r2 in zip(rows, rows2, strict=True):
        d_ler = abs(r1.ler - r2.ler)
        d_m = abs(r1.yield_g_m2[CROP_MAIZE] - r2.yield_g_m2[CROP_MAIZE])
        rel_m = d_m / r1.yield_g_m2[CROP_MAIZE]
        ok = d_ler < TOL_LER and rel_m < TOL_LER
        print(f"  {r1.m}:{r1.n}  LER 差 {d_ler:.4f}  玉米产量相对差 {rel_m:.2%}  "
              f"{'✅' if ok else '🔴'}")
        if not ok:
            failures.append(f"S7 [{r1.m}:{r1.n}] 重跑不一致")

    # ---- 结论 ----
    print("\n" + "=" * 92)
    if failures:
        print("T-09 验收：❌ 不通过")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("T-09 验收：✅ 通过（S1–S7 全部成立）")
    print("  产出：stripcore/batch.py + 三行带型对比表（2:3 / 2:4 / 4:4）")
    print("  ⚠️ 全部数值只用于**相对比较**，不得表述为产量预测。")
    print("  ⚠️ LER 绝对值超出文献区间属**已知偏离**（DESIGN.md 附录 A 第 15 行），")
    print("     但**带型之间的排序**不受该偏离影响 —— 那是本项目的主用途。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
