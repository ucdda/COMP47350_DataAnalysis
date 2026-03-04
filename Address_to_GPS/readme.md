# Address -> GPS (Mapbox) 使用说明

## 1. 获取 Mapbox Token
1. 访问 [Mapbox](https://www.mapbox.com/) 并登录。
2. 进入账户的 API Tokens 页面。
3. 创建一个 token，确保有 Geocoding API 权限。

## 2. 运行前准备
```bash
cd /Users/alex/Documents/COMP47350_DataAnalysis/group_work
export MAPBOX_ACCESS_TOKEN='你的token'
```

## 3. 基础运行
脚本位置：
`COMP47350_DataAnalysis/Address_to_GPS/mapbox_geocode_preview.py`

默认行为：
- 默认输出文件：`COMP47350_DataAnalysis/Address_to_GPS/ppr-group-25208508-train-lab3-preview-geocoded.csv`
- 默认 `--limit=1000`
- 不加 `--resume` 时会覆盖输出文件

示例：
```bash
python3 COMP47350_DataAnalysis/Address_to_GPS/mapbox_geocode_preview.py
```

## 4. 断点续跑（避免覆盖）
如果中途 API 超限或进程中断，使用 `--resume`：

```bash
python3 COMP47350_DataAnalysis/Address_to_GPS/mapbox_geocode_preview.py --resume
```

`--resume` 规则：
- 若输出文件已存在，脚本会读取已完成行（`geocode_status` 非空）。
- 跳过这些行后继续请求并追加写入。
- 不会重写表头，不会覆盖前面已导出的结果。

## 5. 匹配策略（严格 + 模糊回退）
脚本先做严格匹配，再做模糊回退：

1. 严格匹配（高精度）
- `types="address"`
- `autocomplete=False`

2. 严格无结果时（可选）模糊回退
- `types="locality,place,neighborhood,district,region,postcode,street"`
- `autocomplete=True`
- 命中后状态是 `ok_relaxed_area`

如果你只要严格匹配，可禁用回退：
```bash
python3 COMP47350_DataAnalysis/Address_to_GPS/mapbox_geocode_preview.py --no-relax-on-no-result
```

## 6. 如何检查是否已导出
看总行数（含表头）：
```bash
wc -l COMP47350_DataAnalysis/Address_to_GPS/ppr-group-25208508-train-lab3-preview-geocoded.csv
```

看已完成行数（`geocode_status` 非空）：
```bash
python3 - <<'PY'
import csv
p='COMP47350_DataAnalysis/Address_to_GPS/ppr-group-25208508-train-lab3-preview-geocoded.csv'
with open(p, newline='', encoding='utf-8') as f:
    r = csv.DictReader(f)
    done = sum(1 for row in r if (row.get('geocode_status') or '').strip())
print(done)
PY
```

## 7. 限流与稳定性建议
- Geocoding API 超限会返回 `HTTP 429 Too Many Requests`。
- 当前 `sleep=0.05` 约 20 req/s（约 1200/min），可能触发限流。
- 建议调到 `--sleep 0.08` 到 `--sleep 0.1` 更稳。

示例：
```bash
python3 COMP47350_DataAnalysis/Address_to_GPS/mapbox_geocode_preview.py --resume --sleep 0.1
```
