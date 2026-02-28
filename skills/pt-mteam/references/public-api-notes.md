# M-Team 公共 API 公开信息摘要

> 说明：本文件仅整理公开可见信息，接口细节以站点实际文档与返回结果为准。

## 1) 鉴权方式

- 第三方工具建议使用 API Access Token
- HTTP Header：`x-api-key: <token>`
- 公开说明指出不建议继续用 cookie 方式调用接口

## 2) 第三方不允许调用（公开清单）

- `/admin/**`
- `/login`
- `/apikey/**`

## 3) 公布的可调用示例（节选）

`/member/**` 下（公开页列出）：

- `/member/profile`
- `/member/base`
- `/member/bases`
- `/member/sysRoleList`
- `/member/getUserTorrentList`
- `/member/getCrimeRecords`
- `/member/queryUserLoginHistory`

`/msg/**` 下（公开页列出）：

- `/msg/statistic`
- `/msg/notify/statistic`

## 4) 公开建议速率（节选）

- 下载种子配额：1000/天
- 下载种子行为：100/小时
- `/torrent/detail`：100/小时
- `/torrent/search`：1000/近24小时

## 5) 域名与可用性

- 社区生态（索引器/自动化工具）有公开信息提到 API 域名切换至：
  - `api.m-team.cc`
  - `api.m-team.io`
- 生产实现应支持 base URL 配置与域名切换。

## 6) 工程建议

- 统一封装请求：超时、重试、日志、错误分级
- 429/5xx 用指数退避；401/403 不盲目重试
- 给高频接口单独限流器（search/detail）
- 保留“最小可用集”：先做 member/msg，再逐步开放 torrent 能力
