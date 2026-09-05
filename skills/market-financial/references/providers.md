# Providers 配置

一次安装全部可选依赖：`pip install -r requirements.txt`（建议在 `skills/market-financial/.venv` 中）。

## 1) OKX（公共接口）

无需 API key（查询 ticker）。

示例 symbol：
- 现货：`BTC-USDT`
- 永续：`BTC-USDT-SWAP`

## 2) IBKR（ib_insync）

安装：

```bash
pip install ib-insync
```

需要先启动 TWS 或 IB Gateway，并开启 API。

环境变量（可选）：
- `IBKR_HOST` 默认 `127.0.0.1`
- `IBKR_PORT` 默认 `7497`
- `IBKR_CLIENT_ID` 默认 `77`

## 3) Longbridge OpenAPI（直连）

安装：

```bash
pip install longport
```

环境变量（必须）：
- `LONGPORT_APP_KEY`
- `LONGPORT_APP_SECRET`
- `LONGPORT_ACCESS_TOKEN`

可选环境变量：
- `LONGPORT_HTTP_URL`（自定义网关地址时使用）

说明：
- 通过官方 SDK 直连 OpenAPI，使用 key+secret+token。
- 股票示例 symbol：`700.HK`、`AAPL.US`
- 期权查询流程：
  1) `option_chain_expiry_date_list(symbol)` 获取可用到期日
  2) `option_chain_info_by_date(symbol, expiry)` 获取执行价与合约映射
  3) `option_quote([option_symbol])` 获取该期权实时行情


## 4) yfinance（期权兜底）

安装：

```bash
pip install yfinance
```

说明：
- 免费免 API key。
- 当前建议用于期权查询兜底（当 Longbridge USOption 权限不可用时）。

## 5) 自动路由配置（可选）

不传 `--provider` 时，脚本按下面顺序读取路由配置；都没有则用内置默认（crypto → `okx`，equity → `longbridge`，无兜底）：

1. 环境变量 `MARKET_ROUTES_JSON`（内联 JSON）
2. 环境变量 `MARKET_ROUTES_FILE` 指向的 JSON 文件
3. `~/.config/market-financial/routes.json`

示例：

```json
{
  "crypto": { "spot": "okx" },
  "equity": { "stock": "longbridge", "option": "longbridge", "kline": "longbridge" },
  "fallback": { "option": ["yfinance"], "stock": ["ibkr", "yfinance"] }
}
```

- `crypto` / `equity`：按 `--asset` 选主渠道，缺省回落到 `spot` / `stock` 的值。
- `fallback`：主渠道失败时按顺序尝试的渠道列表。
