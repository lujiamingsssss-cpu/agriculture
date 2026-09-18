"""《带型》StripDesign 计算层。

职责（`docs/DESIGN.md` §3）：纯 Python 数值计算，**不得依赖前端或渲染层**。
阶段一只做计算层 + 出图；前端交互与 Blender 渲染属于阶段二。

模块分工：
    conventions.py  坐标系、角度、单位（`docs/CONVENTIONS.md` 的唯一代码落点）
    geometry.py     条带布局的纯几何计算（不依赖 pyhelios）
    scenario.py     场景配置的加载与校验
    scene.py        把场景注入 pyhelios 三维几何（唯一依赖 pyhelios 的模块）
"""

__all__ = ["conventions", "geometry", "scenario", "scene"]
