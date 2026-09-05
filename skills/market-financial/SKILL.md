---
name: market-financial
description: Query market data for crypto, stocks, and options across OKX, IBKR, Longbridge OpenAPI, and Yahoo Finance (yfinance) via one unified CLI script. Use when users ask for quote checks, option chain snapshots, strike selection, and cross-source sanity checks before trading decisions.
---

# market-financial

用一个脚本统一查询多源行情：`okx` / `ibkr` / `longbridge` / `yfinance`。

## 快速开始

```bash
python3 scripts/market_quote.py --provider okx --symbol BTC-USDT --pretty
python3 scripts/market_quote.py --provider ibkr --symbol COIN --asset stock --pretty
python3 scripts/market_quote.py --provider longbridge --symbol AAPL.US --asset stock --pretty
python3 scripts/market_quote.py --provider longbridge --symbol AAPL.US --asset option --expiry 2026-06-18 --strike 300 --right call --pretty
python3 scripts/market_quote.py --provider yfinance --symbol COIN --asset option --expiry 2026-06-18 --strike 300 --right call --pretty
python3 scripts/market_quote.py --provider longbridge --symbol 3690.HK --asset kline --period 1m --count 30 --pretty
```

## 渠道说明

- `okx`: 数字货币现货/永续 ticker（公共接口）。
- `ibkr`: 通过 `ib_insync` 连接 TWS/IB Gateway（更接近交易端口径）。
- `longbridge`: 长桥 OpenAPI 直连（key + secret + token）。
- `yfinance`: 期权兜底查询（免费源，可能延迟）。

## 常用参数

- `--provider` 可选：`okx|ibkr|longbridge|yfinance`
  - 不传 `--provider` 时按路由配置自动选择（默认加密货币走 `okx`，股票/期权走 `longbridge`），配置方式见 `references/providers.md`
- `--symbol` 必填：如 `COIN`、`AAPL.US`、`BTC-USDT`
- `--asset` 可选：`spot|stock|option|kline`（默认 `spot`）
- 期权参数：`--expiry YYYY-MM-DD --strike 300 --right call|put`
- `--period`：K线周期（如 `1m`/`5m`/`15m`/`30m`/`60m`/`1d`/`1w`/`1mo`）
- `--count`：K线条数（默认 20）
- `--pretty`：格式化 JSON 输出

## 渠道前置配置

先看：`references/providers.md`。依赖按需安装：`pip install -r requirements.txt`（`okx` 无需额外依赖）。

关键环境变量：
- IBKR: `IBKR_HOST` `IBKR_PORT` `IBKR_CLIENT_ID`
- Longbridge(OpenAPI): `LONGPORT_APP_KEY` `LONGPORT_APP_SECRET` `LONGPORT_ACCESS_TOKEN`

## 输出与错误

- 成功：stdout 一行 JSON，含 `routed_provider` / `tried_providers`；若经过兜底，`fallback_errors` 记录各渠道失败原因。
- 失败：stderr 输出 `{"error": ...}`，退出码 1。所有渠道失败时 error 中含每个渠道的具体报错。
- 数值字段缺失或为 NaN 时输出 `null`。

## 护栏

- 仅做查询，不下单。
- 优先返回时间戳与来源，避免把延迟数据当成实时成交价。
- 当多源冲突时，以券商终端/交易所直连源为准。
