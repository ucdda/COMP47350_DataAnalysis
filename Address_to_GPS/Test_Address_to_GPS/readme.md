# Test 数据集 Address -> GPS 使用说明

本目录是测试集专用流程，对应 `step1 ~ step5`，与 `Address_to_GPS` 训练集流程一致。  
默认起始输入为项目根目录的 `ppr-group-25208508-test.csv`。

## 脚本流程

1. `step1_geocode.py`：地址 -> 经纬度（仅处理 `County=Dublin`）
2. `step2_districts.py`：经纬度 -> `dublin_district`（无法解析写 `-1`）
3. `step3_map_preview.py`：`districted` 可视化（含参考分割线）
4. `step4_rematch.py`：对 Dublin 且 `dublin_district=-1` 按三区规则重分类（25/26/27）
5. `step5_map_preview.py`：`rematch` 结果可视化

## Mapbox API Key（建议配置）

`step1_geocode.py` 和 `step2_districts.py` 都支持 Mapbox：

- `step1`：先尝试 Nominatim，Nominatim 失败时用 Mapbox 兜底
- `step2`：优先用 Mapbox 反向解析区号，失败再回退 Nominatim

可用两种方式传入 Key：

### 方式 A：环境变量（推荐）

```bash
export MAPBOX_ACCESS_TOKEN='你的_mapbox_api_key'
```

### 方式 B：命令行参数

- `step1`：`--mapbox-token`
- `step2`：`--token`

## 全流程运行示例

下面示例都在项目根目录执行。

```bash
# 0) 可选：先设置 Mapbox API Key（推荐）
export MAPBOX_ACCESS_TOKEN='你的_mapbox_api_key'

# 1) 从测试集起步（默认输入就是 ../ppr-group-25208508-test.csv）
python3 Test_Address_to_GPS/step1_geocode.py
# 若不用环境变量，也可：
# python3 Test_Address_to_GPS/step1_geocode.py --mapbox-token '你的_mapbox_api_key'

# 2) 用 step1 产物做区号解析（把输入替换为上一步输出文件名）
python3 Test_Address_to_GPS/step2_districts.py --input geocoded-test-YYYYMMDD-HHMMSS.csv
# 若不用环境变量，也可：
# python3 Test_Address_to_GPS/step2_districts.py --input geocoded-test-YYYYMMDD-HHMMSS.csv --token '你的_mapbox_api_key'

# 3) 预览 districted 地图
python3 Test_Address_to_GPS/step3_map_preview.py --input districted-test-YYYYMMDD-HHMMSS.csv

# 4) rematch -1
python3 Test_Address_to_GPS/step4_rematch.py --input districted-test-YYYYMMDD-HHMMSS.csv

# 5) 预览 rematch 地图
python3 Test_Address_to_GPS/step5_map_preview.py --input rematch-test-YYYYMMDD-HHMMSS.csv
```

## 输出文件位置

- 所有输出默认写在 `Test_Address_to_GPS/` 目录中。
- 典型输出前缀：
  - `geocoded-test-*.csv`
  - `districted-test-*.csv`
  - `rematch-test-*.csv`
  - `geocode_test_map_demo_osm.html`
  - `rematch_test_map_demo_osm.html`

