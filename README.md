# skills

Monorepo of agent skills (plain `SKILL.md` + scripts; works with any agent that can read a skill folder and run shell commands). Each skill lives in `skills/<name>/` with a `SKILL.md` (frontmatter + usage) and optional `scripts/`, `references/`, `bin/`.

## Included

| Skill | What it does | Required env |
| --- | --- | --- |
| `skills/12306-train` | 12306 direct/transfer ticket query, prices, route (stops) | none |
| `skills/amap-spaces` | AMap (Gaode) Web Service API CLI (`amap`): POI / geocode / route | `AMAP_API_KEY` |
| `skills/market-financial` | Unified quotes for crypto / stocks / options / kline via OKX, IBKR, Longbridge, yfinance | `LONGPORT_*` (Longbridge only), `IBKR_*` optional |
| `skills/pt-mteam` | M-Team PT public API client with rate limiting and endpoint guardrails | `MTEAM_API_KEY` |

## Layout conventions

- `SKILL.md` — frontmatter (`name`, `description`, optional `homepage`) followed by agent-facing usage notes.
- `scripts/` — runnable entry points (`python3 scripts/<x>.py ...`), stdlib-only unless a `requirements.txt` says otherwise.
- `references/` — background docs and cached data; generated caches are git-ignored.
- `bin/` — bundled CLIs (e.g. `amap`).

## Notes

- API keys and per-skill config are read from environment variables only (see each `SKILL.md`), and are **not** committed.
- Per-skill virtualenvs (`.venv/`), caches (`.cache/`) and station data are git-ignored.
