# 渠道配置

依赖全部可选，按需安装：`pip install -r requirements.txt`（建议放在 `skills/market-quote/.venv`）。

## okx

公共接口，无需 key。symbol：现货 `BTC-USDT`，永续 `BTC-USDT-SWAP`（也接受 `BTC/USDT`、`BTC-USDT-PERP`）。K 线周期：1m 3m 5m 15m 30m 1h 2h 4h 6h 12h 1d 1w 1mo。

## longbridge

```bash
pip install longport
export LONGPORT_APP_KEY=...
export LONGPORT_APP_SECRET=...
export LONGPORT_ACCESS_TOKEN=...
# 可选：LONGPORT_HTTP_URL 自定义网关
```

symbol：`700.HK`、`AAPL.US`；裸美股代码自动补 `.US`。期权流程：到期日列表 → 该到期日行权价与合约 → 合约行情。K 线周期支持 1m 到 1y。

## yfinance

```bash
pip install yfinance
```

免费、免 key，可能延迟。symbol：`AAPL`（`AAPL.US` 自动去后缀），港股自动补成 4 位 `0700.HK`。K 线：分钟级最多回溯 7 天（1m）或 60 天，日线 5 年。

## ibkr

```bash
pip install ib-insync
```

需要本地 TWS 或 IB Gateway 运行并开启 API。环境变量可选：`IBKR_HOST`（默认 127.0.0.1）、`IBKR_PORT`（默认 7497）、`IBKR_CLIENT_ID`（默认 77）。目前只实现股票报价，期权/K 线待扩展。

## 路由配置（可选）

不传 `--provider` 时按以下顺序读取，都没有则自动选第一个可用渠道：

1. 环境变量 `MARKET_ROUTES_JSON`（内联 JSON）
2. 环境变量 `MARKET_ROUTES_FILE` 指向的文件
3. `~/.config/market-quote/routes.json`

```json
{
  "crypto": { "quote": "okx", "kline": "okx" },
  "equity": { "quote": "longbridge", "option": "longbridge", "chain": "yfinance", "kline": "longbridge" },
  "fallback": { "quote": ["yfinance", "ibkr"], "option": ["yfinance"] }
}
```

- `crypto` / `equity` 下按子命令名（quote/option/chain/kline）指定主渠道。
- `fallback` 按子命令给出降级顺序；未配置时用其余可用渠道兜底。
