---
name: pt-mteam
description: Access M-Team PT public API with x-api-key authentication for member/profile stats and torrent-related calls. Use when building scripts, bots, indexers, or automations that query M-Team data safely with rate limiting and allowed-endpoint guardrails.
homepage: https://wiki.m-team.cc/zh-tw/api
metadata:
  {
    "openclaw": {
      "requires": { "env": ["MTEAM_API_KEY"] },
      "primaryEnv": "MTEAM_API_KEY"
    }
  }
---

# pt-mteam

使用 M-Team 的开放 API（`x-api-key`）进行安全调用，默认避免高风险/禁用接口。

## 1) 前置要求

- 已在 M-Team 控制台获取 Access Token（API Key）
- 通过请求头传递：`x-api-key: <YOUR_TOKEN>`
- API Base 建议优先：`https://api.m-team.cc`

- 脚本默认附带 `user-agent: Mozilla/5.0`（降低被 Cloudflare 1010 风控拦截概率）
- 可选备用：`https://api.m-team.io`

## 2) 快速调用（CLI）

```bash
python3 scripts/mteam_api_probe.py \
  --base https://api.m-team.cc \
  --api-key "$MTEAM_API_KEY" \
  --method POST \
  --path /api/member/profile \
  --json '{}'
```

POST 示例：

```bash
python3 scripts/mteam_api_probe.py \
  --base https://api.m-team.cc \
  --api-key "$MTEAM_API_KEY" \
  --method POST \
  --path /api/torrent/search \
  --json '{"keyword":"test","pageNumber":1,"pageSize":20}'
```

## 3) 护栏（必须遵守）

- 不调用以下路径：
  - `/admin/**`
  - `/login`
  - `/apikey/**`
- 不用 cookie 模式伪装第三方工具，统一用 `x-api-key`
- 遇到 401/403：停止重试并提示用户检查 token/权限
- 实施限速：
  - 默认最小间隔 `>= 1s/请求`（脚本已实现跨进程限流）
  - `/torrent/detail` 默认 `>= 36s/次`
  - `/torrent/search` 默认 `>= 90s/次`（保守值，可通过参数调整）

## 4) 推荐实践

- 封装统一请求函数：
  - 注入 headers
  - 统一超时（10~20s）
  - 429/5xx 指数退避重试（含 jitter）
- 记录结构化日志（status、path、耗时、重试次数）
- 对外暴露“只读能力”为主（查询、统计、详情）

## 5) 参考资料

- 公开规则与限速摘要：`references/public-api-notes.md`
