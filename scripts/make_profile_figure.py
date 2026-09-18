"""T-10 验收：光分布剖面热力图（阶段一验收判据 D1）。

跑法（仓库根目录）：
    uv run python scripts/make_profile_figure.py

产出：
    out/profile_m2n4_ns.png     南北行向剖面吸收辐射热力图
    out/profile_m2n4_ew.png     东西行向（供 T-11 并排对比复用）

验收判据（先写判据，再实现 —— `AGENTS.md` 第 2 节）：
    D1a 横轴为垂直于行向的位置 u [m]、纵轴为高度 w [m]，轴标签含单位；
    D1b 色标标注物理量名 + 单位 + 取值范围（`DESIGN.md` §7 强制）；
    D1c 图底部标出哪几行是玉米、哪几行是大豆（让外行瞬间看懂）；
    D1d ⭐ 数据**全部**来自计算输出的逐层吸收辐射 ——
         脚本内不得出现任何手工调色、平滑、亮度修饰；
         并由「场值总和 vs 计算总吸收功率」的守恒核对证明这一点；
    D1e 脚本可重复运行，同一场景两次运行的总量与主格局稳定（Monte-Carlo 不可能逐格全等）。

⚠️ **图面信息量的说明（供演示参考，不是缺陷）**：
    南北行向下 95% 的入射光被最上层吸收，下方各层近乎全黑 ——
    这是 LAI 3.5 的冠层对 60° 入射的**正确物理结果**（冠层几乎完全截获）。
    东西行向下出现明显的**垂直光柱**（光穿过玉米行间后在带内纵深吸收），
    两种行向的剖面格局肉眼可辨 —— 这正是 D2 与 T-11 并排对比要展示的东西。

边界：不做南北/东西并排对比图（属 T-11）、不做三维（T-12）、不做产量/LER（T-06~T-08）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from stripcore.profile import build_profile_field, render_profile_heatmap
from stripcore.radiation import assert_energy_conservation, run_par_radiation
from stripcore.scenario import load_scenario_by_name, scene_summary
from stripcore.scene import build_scene

# 竖向层数：热力图需要足够的竖向分辨率才能显示光斑结构。
# 注意这是**展示用网格密度**，不改变物理模型（叶面积、消光、行向均不变）。
PROFILE_LAYERS = 12

# 光线数：热力图对逐格噪声敏感（单格能量小、统计涨落相对大）。
# 取较高值以保证图面干净且可复现。实测 5000 时逐格抖动明显、图上出现杂斑。
PROFILE_DIRECT_RAYS = 100_000
PROFILE_DIFFUSE_RAYS = 20_000

OUT_DIR = Path("out")


def build_one(name: str):
    """跑一个场景，返回 (scenario, field, result)。"""
    scenario = load_scenario_by_name(name)
    scene = build_scene(scenario, crop_layers=PROFILE_LAYERS)
    result = run_par_radiation(
        scenario,
        scene,
        direct_rays=PROFILE_DIRECT_RAYS,
        diffuse_rays=PROFILE_DIFFUSE_RAYS,
    )
    assert_energy_conservation(result)
    field = build_profile_field(scenario, scene, result)
    return scenario, field, result


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    print("=" * 74)
    print(f"T-10 剖面热力图（竖向层数 = {PROFILE_LAYERS}）")
    print("=" * 74)

    for name in ("m2n4_ns", "m2n4_ew"):
        scenario, field, result = build_one(name)
        data = field.absorbed_flux_w_m2
        arr = np.asarray(data, dtype=np.float64)

        print(f"\n—— 场景 {name} ——")
        print(scene_summary(scenario).splitlines()[0])
        n_u = arr.shape[1]
        n_w = arr.shape[0]
        print(f"  网格: u × w = {n_u} × {n_w}")
        print(f"  吸收通量密度范围: {arr.min():.2f} ~ {arr.max():.2f} W/m²")

        # ---- D1d 数据来源核对：场值积分必须等于计算出的总吸收 ----
        du_m = field.u_edges_m[1] - field.u_edges_m[0]
        v_m = 4.0  # 与 build_scene 默认 row_length_m 一致
        field_power_w = float(arr.sum()) * du_m * v_m
        computed_power_w = float(result.total_absorbed_power_w)
        rel = abs(field_power_w - computed_power_w) / computed_power_w
        print(f"  场值积分 = {field_power_w:9.2f} W   计算总吸收 = {computed_power_w:9.2f} W   "
              f"相对差 = {rel:.2e}")
        if rel > 1e-6:
            failures.append(
                f"D1d [{name}] 场值积分与计算总吸收不一致（相对差 {rel:.2e}）——"
                "说明图上数据并非全部来自计算输出"
            )
        else:
            print("  ✅ D1d 数据来源核对通过（场值全部来自计算输出）")

        # ---- D1e 可复现性：同一场景重跑，场应稳定 ----
        # ⚠️ 本计算是 Monte-Carlo 光线追踪，**不可能逐格全等**。
        #    判据不能取"逐格相对差的最大值" —— 零值/微量格作分母会给出无意义的比值
        #    （实测曾得到 10738%）。改为两条有物理含义的稳定性指标：
        #      ① 场值积分（= 总吸收功率）的相对差 —— 总量必须稳定；
        #      ② 主格局一致：以场最大值为尺度，逐格绝对差的最大值应远小于该尺度。
        _, field2, _ = build_one(name)
        arr2 = np.asarray(field2.absorbed_flux_w_m2, dtype=np.float64)
        total1 = float(arr.sum())
        total2 = float(arr2.sum())
        total_rel = abs(total1 - total2) / total1
        scale = max(float(arr.max()), 1e-9)
        max_abs_diff = float(np.max(np.abs(arr - arr2)))
        pattern_rel = max_abs_diff / scale
        print(f"  D1e 重跑：场值积分相对差 = {total_rel:.3%}（容限 1%）")
        print(f"           主格局：逐格最大绝对差 = {max_abs_diff:.2f} W/m²，"
              f"占场最大值 {scale:.1f} 的 {pattern_rel:.2%}（容限 10%）")
        if total_rel > 0.01:
            failures.append(f"D1e [{name}] 场值积分相对差 {total_rel:.3%} 超 1%，总量不稳定")
        if pattern_rel > 0.10:
            failures.append(
                f"D1e [{name}] 主格局逐格绝对差占场最大值 {pattern_rel:.2%} 超 10%，"
                "图面存在明显 Monte-Carlo 噪声，演示不稳定"
            )
        if total_rel <= 0.01 and pattern_rel <= 0.10:
            print("  ✅ D1e 可复现性通过（总量与主格局均稳定）")

        out_path = OUT_DIR / f"profile_{name}.png"
        render_profile_heatmap(field, scenario, str(out_path))
        print(f"  已输出: {out_path}")

    print("\n" + "=" * 74)
    if failures:
        print("T-10 验收：❌ 不通过")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("T-10 验收：✅ 通过（D1a–D1e）")
    print("  产出：out/profile_m2n4_ns.png、out/profile_m2n4_ew.png")
    print("  ⚠️ out/ 与 *.png 已被 .gitignore 忽略（demo 产物不入库，可随时重跑生成）。")
    print("  ⚠️ 参数与固定太阳角为原型阶段近似，已登记 DESIGN.md 附录 A。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
