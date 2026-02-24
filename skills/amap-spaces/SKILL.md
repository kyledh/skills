---
name: amap-spaces
description: Query AMap (Gaode) Web Service APIs for POI search, nearby search, geocode, reverse geocode, and details via a fast CLI.
homepage: https://lbs.amap.com/
metadata:
  {
    "openclaw": {
      "emoji": "🧭",
      "requires": { "bins": ["amap"], "env": ["AMAP_WEB_API_KEY"] },
      "primaryEnv": "AMAP_WEB_API_KEY",
      "install": [
        {
          "id": "local-node",
          "kind": "node",
          "package": "(local)",
          "bins": ["amap"],
          "label": "Use bundled amap CLI (node script)"
        }
      ]
    }
  }
---

# amap-spaces (高德 Web API)

用高德地图「Web 服务 API」做 POI 搜索/周边/地理编码等，不走浏览器。

## Prereq

- 环境变量 `AMAP_WEB_API_KEY` 必须设置（高德 Web 服务 Key）

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
