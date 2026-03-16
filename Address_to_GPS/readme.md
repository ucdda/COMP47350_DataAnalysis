# Address -> GPS 使用说明

本目录提供从地址到经纬度（地理编码）以及从经纬度到都柏林行政区号的完整流程，涉及多个脚本与 API（Mapbox、Nominatim）。

---

## 原始数据处理流程概览

### multi_api_calling.py：地址 → 经纬度

**输入数据**  
- 默认输入：`../ppr-group-25208508-train.csv`（可通过 `--input` 指定）
- 依赖列：`Address`、`County`

**处理逻辑**  
1. **行级过滤**：仅对 `County` 为 **Dublin**（不区分大小写）的行发起地理编码；非 Dublin 行原样写入输出，并补空列 `geocode_status`、`latitude`、`longitude`、`geocode_provider`，不调用任何 API。
2. **查询构造**：对 Dublin 行用 `Address` 和 `County` 构造查询字符串。若 County 未出现在 Address 文本中，则拼接为 `"{Address}, {County}, Ireland"`，否则为 `"{Address}, Ireland"`。
3. **地理编码顺序**：  
   - 先调用 **Nominatim**（OpenStreetMap）前向地理编码；  
   - 若 Nominatim 无结果或请求出错，且配置了 `MAPBOX_ACCESS_TOKEN`，则用 **Mapbox** 兜底：  
     - 先严格匹配（`types=address`，`autocomplete=False`）；  
     - 若无结果再松弛匹配（`types=locality,place,neighborhood,district,region,postcode,street`，`autocomplete=True`）。
4. **输出**：在原始 CSV 列基础上追加四列：`geocode_status`、`latitude`、`longitude`、`geocode_provider`。输出文件名为 `geocoded-{YYYYMMDD-HHMMSS}.csv`（前缀可通过 `--output` 修改）。
5. **限流**：每次实际发起请求后 `time.sleep(1.0)`，以符合 Nominatim/Mapbox 使用策略。

**状态含义**  
- `ok_nominatim`：Nominatim 成功返回坐标  
- `ok_mapbox_strict`：Mapbox 严格地址匹配成功  
- `ok_mapbox_relaxed`：Mapbox 松弛（区域级）匹配成功  
- `no_result`：两个 API 均无结果  
- `error`：请求异常  
- `empty_query`：地址为空未查询  

---

### district_api.py：经纬度 → 都柏林区号

**输入数据**  
- 输入：已带经纬度的 CSV（通常为 `multi_api_calling.py` 生成的 `geocoded-*.csv`），需包含列：`County`、`latitude`、`longitude`。

**处理逻辑**  
1. **行级过滤**：仅对 `County` 为 **Dublin** 且 `latitude`/`longitude` 可解析为浮点数的行进行反向地理编码；其余行原样写入，`dublin_district` 列为空。
2. **反向地理编码顺序**：  
   - 若提供 `MAPBOX_ACCESS_TOKEN`，优先调用 **Mapbox** 反向地理编码（`types=postcode,place,region`）；  
   - 若 Mapbox 未返回有效都柏林区号，则回退到 **Nominatim** 反向地理编码（`addressdetails=1`）。
3. **都柏林判定**：根据返回的 city/county/place_name/context 等是否包含 "Dublin" 或 "都柏林" 判断是否在都柏林范围内。
4. **区号解析**：从 postcode（如 `"D01 P5P5"`、`"D6W"`）提取区号：取第一个以空格分隔的 token，若以 D/d 开头则去掉首字母，取其后最多两位；若第一位为 `0` 则只保留第二位（如 `"01"` → `"1"`），否则保留两位（如 `"12"`、`"6W"`）。
5. **输出**：在原有列基础上增加一列 `dublin_district`。  
   - Dublin 行且成功解析：写入区号（如 `"1"`、`"8"`、`"6W"`）；  
   - Dublin 行但无法解析区号：写入 `"-1"` 便于后续统计；  
   - 非 Dublin 行：留空。  
   输出文件名为 `districted-{YYYYMMDD-HHMMSS}.csv`（前缀可通过 `--output-prefix` 修改）。
6. **限流**：每次反向地理编码请求后 `time.sleep(1.0)`。

**典型用法**  
- 单点：`python district_api.py --lat 53.3498 --lon -6.2603`  
- 批量：`python district_api.py --input geocoded-20260310-215024.csv`（可加 `--limit N`、`--output-prefix`、`--token`）

**推荐流水线**：先用 `multi_api_calling.py` 从原始训练 CSV 得到 `geocoded-*.csv`，再用 `district_api.py` 以该文件为 `--input` 得到带 `dublin_district` 的 `districted-*.csv`。

---

### mapdemonstration.py：地理编码结果地图预览

**作用**  
将 geocoded CSV 生成一张交互式 HTML 地图（OpenStreetMap + Leaflet），用圆点区分成功/失败，便于检查地理编码效果。

**输入数据**  
- 默认输入：`geocoded-20260310-123456.csv`（可通过 `--input` 指定，通常为 `multi_api_calling.py` 输出的 `geocoded-*.csv`）
- 依赖列：`Address`、`County`、`geocode_status`、`latitude`、`longitude`（若有 `geocode_query` 会在弹窗中显示）
- 相对路径会按脚本所在目录（`Address_to_GPS/`）解析

**成功/失败判定**  
- **成功（红点）**：`geocode_status` 为 `ok_nominatim`、`ok_mapbox_strict` 或 `ok_mapbox_relaxed`，且 `latitude`、`longitude` 有效。
- **失败（灰点）**：其余情况。没有有效经纬度的行也算失败。

**圆点位置**  
- 成功点、以及有经纬度的失败点：使用 CSV 中的 `latitude`、`longitude`。  
- 没有经纬度的失败点：先尝试用同 County 成功点的平均坐标（县中心）；若该 County 无成功点则落在爱尔兰中心 `(53.425, -7.944)`。这样所有记录都会出现在图上，但无坐标的灰点位置仅为占位。

**输出**  
- 默认输出：`geocode_map_demo_osm.html`（在 `Address_to_GPS/` 下），用浏览器打开即可。左上角有成功数、失败数、总数与成功率。

**用法**  
```bash
# 使用默认输入 geocoded-20260310-123456.csv
python3 Address_to_GPS/mapdemonstration.py

# 指定 geocoded 文件与输出 HTML
python3 Address_to_GPS/mapdemonstration.py --input geocoded-20260310-215024.csv --output my_map.html
```

---

## 1. 获取 Mapbox Token
1. 访问 [Mapbox](https://www.mapbox.com/) 并登录。
2. 进入账户的 API Tokens 页面。
3. 创建一个 token，确保有 Geocoding API 权限。

## 2. 运行前准备
在项目根目录或 `Address_to_GPS` 目录下执行前，可设置 Mapbox Token（`multi_api_calling.py` 与 `district_api.py` 的 Mapbox 兜底/反向地理编码会用到）：

```bash
export MAPBOX_ACCESS_TOKEN='你的token'
```

地理编码主流程（推荐）：
```bash
# 1）地址 → 经纬度（仅处理 County=Dublin，输出 geocoded-*.csv）
python3 Address_to_GPS/multi_api_calling.py --input ../ppr-group-25208508-train.csv

# 2）经纬度 → 都柏林区号（输出 districted-*.csv）
python3 Address_to_GPS/district_api.py --input geocoded-YYYYMMDD-HHMMSS.csv
```
