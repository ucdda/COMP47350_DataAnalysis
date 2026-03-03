# 第一部注册并获取 Mapbox API Token

1. 访问 [Mapbox 官网](https://www.mapbox.com/)。
2. 注册一个账户（尽可能不绑卡）。
3. 登录后进入账户设置，找到 API Tokens 页面。
4. 创建一个新的 token，确保勾选了 Geocoding API 的权限。

# 修改了默认值为500，以避免过多的API请求导致被扣钱。

parser.add_argument(
"--limit",
type=int,
default=500,
help="Maximum number of rows to process.",
)

# 初始化操作代码 bash:

cd /Users/alex/Documents/COMP47350_DataAnalysis/group_work
export MAPBOX_ACCESS_TOKEN='你的token'
python3 COMP47350_DataAnalysis/scripts/mapbox_geocode_preview.py

# 限流分析

按 Mapbox 官方文档（截至我刚查到的页面）：

Geocoding API 默认是 1000 requests/minute（按 token 计数）
超限会返回 HTTP 429 Too Many Requests
这个默认值可以按账号调整（联系 Mapbox）
另外可通过响应头观察限流窗口：

X-Rate-Limit-Interval（通常 60 秒）
X-Rate-Limit-Limit
X-Rate-Limit-Reset
你的批量脚本现在 sleep=0.05，约 20 req/s（约 1200/min），有可能触发限流。
建议先调到 sleep=0.08 到 0.1（约 600-750/min）更稳。
