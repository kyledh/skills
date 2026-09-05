# skill-12306-train-search

用于**日常少量查询** 12306 的开源脚本/skill：查询直达车次与中转换乘，并展示时间、余票与票价（若 12306 返回）。

> 说明：12306 可能因为限流/风控/网络出口特征返回 HTML 错误页（例如 `mormhweb/error.html`）。本项目会尽量减少请求次数并做失败兜底，但不承诺稳定可用。

## 功能

- **直达查询**：车次 / 出发到达时间 / 历时 / 各席别余票 / 票价
- **中转换乘**：给出中转方案（仅在用户明确允许时使用）
- **站点映射**：自动更新站名 → 站码（telecode）
- **更友好的输入**：
  - 日期可省略（默认查询**明天**）
  - 支持 `YYYY-MM-DD`，也支持 `3.1 / 3-1 / 3/1` 这类简写（自动补当前年）

## 快速开始

### 1) 安装依赖

- Python 3（系统自带即可）

### 2) 站点缓存（自动）

首次查询会自动下载站名→站码映射表，无需手动初始化。之后如需刷新（例如新增车站）再手动执行：

```bash
python3 scripts/update_stations.py
```

### 3) 查询直达

```bash
# 日期可省略（默认查明天，并提示“不同日期可能不同”）
python3 scripts/query_tickets.py --from 北京朝阳 --to 锦州南

# 指定日期
python3 scripts/query_tickets.py --date 2026-03-01 --from 北京朝阳 --to 锦州南 --limit 10

# 日期简写：M-D / M.D / M/D（自动补当前年）
python3 scripts/query_tickets.py --date 3.1 --from 北京朝阳 --to 锦州南
```

### 4) 查询中转（仅在用户允许时）

```bash
python3 scripts/query_transfer.py --date 2026-02-25 --from 密云 --to 锦州 --limit 10
python3 scripts/query_transfer.py --date 2026-02-25 --from 密云 --to 锦州 --middle 承德南 --limit 10
```

## 设计边界（请务必阅读）

- 本项目**只做查询**：不包含登录、验证码处理、下单、抢票、自动刷票等能力。
- 为避免对服务造成压力：
  - 会对相同查询做短时间缓存
  - 遇到异常会退避重试
  - 日期限制在近期开票窗口（按“15 天包含今天”的口径：`today ~ today+14`）

## 合规与风险提示

- 请遵守 12306 的服务条款与相关法律法规。
- 建议仅用于**个人/少量**查询；不要用于高频抓取、商业化数据服务或任何可能影响 12306 正常运行的用途。
- 若频繁返回 HTML 错误页，建议：降低频率、等待一段时间再试，或更换网络出口。

## 常见问题

### 为什么会返回 HTML（mormhweb/error.html）？
这通常是 12306 的限流/风控/网络异常兜底页面。常见处理：
- 减少重试频率，等 5–15 分钟再试
- 换站点组合（锦州/锦州南/锦州北）
- 更换网络出口（往往最有效）

### 为什么默认查“明天”？
用户不提供日期时，查询“今天”可能已经错过部分车次或展示不完整。默认查明天更接近“想了解有哪些车次/大概多少钱”的需求。

## 目录结构

- `scripts/update_stations.py`：更新站点缓存
- `scripts/stations.py`：站点搜索/解析 + 日期规范化（其余脚本共用）
- `scripts/query_tickets.py`：直达查询
- `scripts/query_transfer.py`：中转换乘查询
- `scripts/query_route_stations.py`：车次经停站查询
- `SKILL.md`：skill 定义与使用说明

## License

MIT License. See [`LICENSE`](./LICENSE).
