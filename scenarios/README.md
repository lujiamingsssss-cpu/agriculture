"""场景配置文件目录。

每个 `<name>.json` 描述一个可复现的条带场景（几何 + 固定太阳条件）。

文件格式（字段含义见 `stripcore/scenario.py`）：

    {
      "name": "<场景名>",
      "strip": {
        "m": 玉米行数, "n": 大豆行数,
        "band_width_m": 带宽,
        "row_dir_deg": 行向（0=南北, 90=东西）,
        "h_maize_m": 玉米株高, "h_soy_m": 大豆株高,
        "lai_maize": 玉米 LAI, "lai_soy": 大豆 LAI,
        "n_bands": 计算域覆盖的完整带数（≥2）
      },
      "sun": { "elev_deg": 太阳高度角, "azim_deg": 太阳方位角（从正北顺时针） }
    }

⚠️ **参数出处纪律**：这些数值取自 `docs/PARAMETERS.md` 的默认值，其状态均为「待核实」。
按 `BASELINE.md` §3.4，它们已登记到 `docs/DESIGN.md` 附录 A「临时近似登记表」，
对外演示时必须口头说明"这是原型阶段的近似"。
"""
