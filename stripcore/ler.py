"""土地当量比（LER）计算。对应 `docs/TASKS.md` T-08。

**定义与口径**（本模块最关键的部分，必须无歧义）

`docs/DESIGN.md` §4.5 给出的公式是：

    LER = (Y_maize_inter / Y_maize_solo) + (Y_soy_inter / Y_soy_solo)

但该式在间作语境下有**两种互不相同的口径**，两者数值差别很大，必须分别说明：

**口径 A（份额加权，农学标准口径）**
    LER 的原义是"需要多少倍的单作土地才能产出间作的全部产量"。
    间作中每种作物只占**一部分土地**（面积份额 `f_c`），其贡献应以占地为权重：

        LER_A = Y_c_inter/Y_c_solo × f_c + Y_s_inter/Y_s_solo × f_s

    其中 `f_c` = 该作物占地 / 总占地，`f_c + f_s = 1`。
    若把 `f` 记成该作物占计算域的面积比，则 `LER_A` 是**标准的土地当量比**。

**口径 B（每公顷产量比之和，未加权）**
    直接代入"各作物相对其**自身占地**的单位面积产量"：

        LER_B = Y_c_inter/Y_c_solo + Y_s_inter/Y_s_solo

    ⚠️ 口径 B **不是**标准 LER：它把两种作物都当作占了整块地，
    因而系统性偏高。它与口径 A 的关系为
        `LER_B − 1 = (LER_A − 1) + (f_c·r_c + f_s·r_s)` 型混合，
    无简单换算；两者必须在报告中**分别标明**，不可混用。

    `DESIGN.md` §4.5 的公式写成"比值之和"，字面更接近口径 B；
    本模块**同时输出两者**并默认以口径 A 为 LER 值（农学标准口径），
    把口径 B 作为附注，避免含糊。

**为什么分子分母必须同模型**（`DESIGN.md` §4.5 的纪律）
    单作基准必须用**同一模型、同一参数集**计算，否则模型系统误差
    不会被抵消，比较无效。本模块只做除法与加权，不引入任何新物理。

⚠️ **绝对量纪律**：LER 只用于**相对比较与情景分析**，
    不得表述为"预测产量"（`AGENTS.md` 第 2 节 / `DESIGN.md` 附录 B）。
"""

from __future__ import annotations

from dataclasses import dataclass

from stripcore.biomass import BiomassResult, crop_ground_area_m2
from stripcore.geometry import CROP_MAIZE, CROP_SOY

LER_LITERATURE_RANGE: tuple[float, float] = (1.0, 1.4)
"""LER 的文献报道区间（`docs/DESIGN.md` §6 判据 C3）。

⚠️ 该区间来自文献（本项目尚未逐条核实原文，属 `PARAMETERS.md` §9 的待办）。
超出该区间**不自动等于算错**，须结合模型机制判断并如实登记。
"""


@dataclass
class CropLER:
    """单作物对 LER 的贡献。"""

    crop: str
    yield_inter_g_m2: float
    """间作下该作物相对**其自身占地**的产量 [g/m²]。"""

    yield_solo_g_m2: float
    """单作下该作物的产量 [g/m²]（同一模型、同一参数集）。"""

    area_share: float
    """该作物在间作中的**占地面积份额**（无量纲，两作物之和为 1）。"""

    @property
    def ratio(self) -> float:
        """产量比 Y_inter / Y_solo（无量纲）。"""
        if self.yield_solo_g_m2 <= 0.0:
            raise ValueError(
                f"{self.crop} 单作基准非正（{self.yield_solo_g_m2}），无法构成 LER"
            )
        return self.yield_inter_g_m2 / self.yield_solo_g_m2

    @property
    def weighted_ratio(self) -> float:
        """按占地份额加权的贡献（口径 A）。"""
        return self.ratio * self.area_share


@dataclass
class LERResult:
    """一次 LER 计算的完整结果。"""

    crops: dict[str, CropLER]
    ler_area_weighted: float
    """口径 A：按占地份额加权 —— **标准土地当量比**（本模块的 LER 值）。"""

    ler_ratio_sum: float
    """口径 B：产量比之和（未加权）—— 仅供对照，不是标准 LER。"""

    @property
    def in_literature_range(self) -> bool:
        """口径 A 是否落在文献区间内。"""
        lo, hi = LER_LITERATURE_RANGE
        return lo <= self.ler_area_weighted <= hi

    def summary(self) -> str:
        """人类可读的一行摘要。"""
        parts = " + ".join(
            f"{c.crop}: {c.ratio:.3f}×{c.area_share:.3f}"
            for c in self.crops.values()
        )
        return (
            f"LER(口径A) = {parts} = {self.ler_area_weighted:.3f}"
            f"；比例和(口径B) = {self.ler_ratio_sum:.3f}"
        )


def compute_ler(
    inter_layout,
    solo: dict[str, BiomassResult],
    inter: BiomassResult,
    row_length_m: float,
) -> LERResult:
    """计算土地当量比（LER）。

    Args:
        inter_layout: 间作的 `StripLayout`（用于算各作物的占地份额）。
        solo: `{作物: 单作结果}`，必须由**同一模型、同一参数集**算出
            （`DESIGN.md` §4.5：否则系统误差不抵消，比较无效）。
        inter: 间作场景的干物质/产量结果（`biomass.compute_biomass`）。
        row_length_m: 沿行向的建模长度 [m]。

    Returns:
        `LERResult`（同时给出两种口径）。

    Raises:
        ValueError: 缺少某作物的间作或单作结果，或单作产量非正。
    """
    areas = {
        crop: crop_ground_area_m2(crop, inter_layout, row_length_m)
        for crop in (CROP_MAIZE, CROP_SOY)
    }
    total_area = sum(areas.values())
    if total_area <= 0.0:
        raise ValueError("间作占地总面积为 0，无法计算面积份额")

    crops: dict[str, CropLER] = {}
    for crop in (CROP_MAIZE, CROP_SOY):
        if crop not in inter.crops:
            raise ValueError(f"间作结果缺少作物 {crop!r}")
        if crop not in solo:
            raise ValueError(f"缺少作物 {crop!r} 的单作基准")
        if crop not in solo[crop].crops:
            raise ValueError(f"单作基准 {crop!r} 中不含该作物")
        crops[crop] = CropLER(
            crop=crop,
            yield_inter_g_m2=inter.crops[crop].yield_g_m2,
            yield_solo_g_m2=solo[crop].crops[crop].yield_g_m2,
            area_share=areas[crop] / total_area,
        )

    weighted = sum(c.weighted_ratio for c in crops.values())
    ratio_sum = sum(c.ratio for c in crops.values())
    return LERResult(
        crops=crops, ler_area_weighted=weighted, ler_ratio_sum=ratio_sum
    )
