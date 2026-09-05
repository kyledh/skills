---
name: amap-spaces
description: Query AMap (Gaode) Web Service APIs for POI search, nearby search, geocode, reverse geocode, and details via a fast CLI.
homepage: https://lbs.amap.com/
---

# amap-spaces (高德 Web API)

用高德地图「Web 服务 API」做 POI 搜索/周边/地理编码等，不走浏览器。

## Prereq

- Node.js 18+（使用内置 `fetch`）
- 环境变量 `AMAP_API_KEY` 必须设置（高德 Web 服务 Key）；可选 `AMAP_TIMEOUT_MS`（默认 15000）
- 可执行文件在 `bin/amap`：直接 `./bin/amap ...`，或把 `bin/` 加入 PATH 后按下文 `amap ...` 调用

## Commands

- 文本搜索（关键词/城市）：
  - `amap poi "密云 烤鱼" --city 北京 --limit 10`

- 周边搜索（经纬度 + 半径米）：
  - `amap around --lat 40.561191 --lng 116.820381 --radius 8000 --keywords "农家院" --limit 10`

- POI 详情（用 POI id）：
  - `amap details <id>`

- 路线规划（驾车/步行）：
  - `amap route driving --origin "116.856,40.390" --dest "116.364,39.907"`
  - `amap route walking --origin "116.856,40.390" --dest "116.364,39.907"`

- 地理编码（地址→坐标）：
  - `amap geocode "北京密云区政府"`

- 逆地理编码（坐标→地址/附近 POI）：
  - `amap regeo --lat 40.561191 --lng 116.820381 --radius 1000`

## Output

默认人类可读；加 `--json` 输出 JSON，方便脚本处理。

## Errors

高德业务错误（如 `INVALID_USER_KEY`、`DAILY_QUERY_OVER_LIMIT`）会以非零退出码 + `AMap error <infocode>: <info>` 输出到 stderr，不会静默返回空结果。
