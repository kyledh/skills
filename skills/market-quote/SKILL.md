---
name: market-quote
description: Read-only market data lookup for crypto, HK/US stocks, options and candles through one CLI with pluggable providers (OKX, Longbridge OpenAPI, Yahoo Finance, Interactive Brokers). Use when the user asks for a current price, bid/ask, an option contract or chain, recent K-line bars, or wants the same quote cross-checked across sources. Never places orders.
---

# market-quote

一个入口脚本 `scripts/market_quote.py`，多渠道可插拔，只查不下单。

## 快速开始

```bash
cd scripts
python3 market_quote.py providers --pretty                 # 看哪些渠道可用及原因
python3 market_quote.py quote BTC-USDT                      # 加密货币，自动走 okx
python3 market_quote.py quote AAPL                          # 股票，自动选第一个可用渠道
python3 market_quote.py quote 700.HK --provider yfinance    # 指定渠道
python3 market_quote.py option AAPL --expiry 2026-12-18 --strike 250 --right put
python3 market_quote.py chain AAPL --expiry 2026-12-18      # 到期日列表 + 该到期日全部行权价
python3 market_quote.py kline BTC-USDT --period 1h --count 50
python3 market_quote.py compare AAPL --providers longbridge,yfinance   # 多源对比
```

所有子命令支持 `--pretty`；成功时 stdout 输出一个 JSON，失败时 stderr 输出 `{"error": ...}` 且退出码 1。

## 子命令

| 子命令 | 作用 | 关键参数 |
| --- | --- | --- |
| `quote SYMBOL` | 最新价、买卖价、日内高低、前收 | `--provider` |
| `option SYMBOL` | 单个期权合约报价，自动取最近到期日和最近行权价 | `--expiry` `--strike` `--right` |
| `chain SYMBOL` | 期权到期日列表 + 指定到期日的行权价/合约列表 | `--expiry`（默认最近） |
| `kline SYMBOL` | K 线 | `--period`（1m 5m 15m 30m 1h 4h 1d 1w 1mo）`--count` |
| `compare SYMBOL` | 同一标的多渠道报价并计算价差，判断是否一致 | `--providers` `--tolerance`（默认 1%） |
| `providers` | 列出渠道、能力、可用性、当前路由配置 | |

## 渠道能力

| 渠道 | 市场 | quote | option | chain | kline | 前置条件 |
| --- | --- | --- | --- | --- | --- | --- |
| `okx` | 加密现货/永续 | ✓ | | | ✓ | 无 |
| `longbridge` | 港美股 | ✓ 含盘前盘后 | ✓ | ✓ | ✓ | `pip install longport` + `LONGPORT_APP_KEY/APP_SECRET/ACCESS_TOKEN` |
| `yfinance` | 美股/港股 | ✓ 可能延迟 | ✓ | ✓ | ✓ | `pip install yfinance` |
| `ibkr` | 美股 | ✓ | | | | `pip install ib-insync` + 本地 TWS/Gateway 开启 API |

symbol 写法：加密 `BTC-USDT` / `BTC-USDT-SWAP`；股票 `AAPL`、`AAPL.US`、`700.HK`。脚本按渠道自动转换（Yahoo 用 `0700.HK`，Longbridge 裸美股代码补 `.US`）。

## 路由规则

1. `--provider` 指定则只用它。
2. 否则读路由配置（见 `references/providers.md`），主渠道失败按 fallback 顺序降级。
3. 没有配置时按市场自动选：加密 → okx；股票 → longbridge、yfinance、ibkr 中第一个**可用**的，其余作为兜底。

输出的 `route` 字段记录模式、尝试过的渠道和各自失败原因。

## 依赖安装

```bash
pip install -r requirements.txt   # 全部可选；okx 无需任何依赖
```

## 护栏

- 仅查询，IBKR 也是只读连接。
- 结果带 `fetched_at` 和渠道时间戳，yfinance 可能延迟 15 分钟，交易决策以券商/交易所直连源为准。
- 多源不一致时用 `compare` 看价差，`stats.consistent` 为 false 说明超过容差。

## 扩展新渠道

在 `scripts/mq/providers/` 新建模块，继承 `mq.base.Provider`，声明 `name` / `markets` / `capabilities`，实现 `available()` 和对应方法，导出 `PROVIDER`，再把模块名加进 `providers/__init__.py` 的 `MODULES`。CLI、路由、compare 自动识别。
