---
name: 12306-train
description: Query China Railway 12306 train tickets (direct + transfer) with remaining seats, prices, and route (stops). Use when the user asks to check train availability/remaining seats/prices or wants to see a train’s stop list. Low-volume queries only; NOT for purchasing, login, captcha, or high-frequency scraping.
---

# 12306 Train Search (low-frequency)

## What this skill does

- Look up station codes (中文站名 → 3-letter code) using cached `station_name.js` parsing.
- Query remaining seats / train list for a given date + route using 12306 public query endpoints.
- Includes seat availability **and prices** per seat type when available.
- Returns structured JSON and a human-readable summary.

## Guardrails (important)

- **Do not** implement buying tickets, account login, captcha bypass, or aggressive concurrency.
- Default to **low frequency**: cache identical queries for ~60s; back off on errors.
- If 12306 blocks or returns unexpected data, **fail gracefully** and suggest manual check. Error responses are never cached; only successful JSON results are (60s for tickets, 120s for transfer).

## Quick usage

### 1) Update station cache (first run; then weekly)

```bash
python3 scripts/update_stations.py
```

### 2) Query direct tickets

Examples:

```bash
python3 scripts/query_tickets.py --date 2026-03-01 --from 上海 --to 杭州
python3 scripts/query_tickets.py --from 上海 --to 杭州  # date omitted → defaults to tomorrow
python3 scripts/query_tickets.py --date 2026-03-01 --from SHH --to HGH
python3 scripts/query_tickets.py --date 2026-03-01 --from 上海虹桥 --to 杭州东 --purpose ADULT --limit 15
```

### 3) Query route stations (stops)

Use this when the user asks “经停/途经哪些站”.

```bash
# If you know the train code
python3 scripts/query_route_stations.py --date 2026-03-01 --from 北京朝阳 --to 锦州南 --train-code K4409

# If you already have train_no
python3 scripts/query_route_stations.py --date 2026-03-01 --from 北京朝阳 --to 锦州南 --train-no 24000K44090U
```

### 4) Query transfer (interline) tickets (only when user allows/asks)

All scripts accept `--date` as `YYYY-MM-DD` or `M-D` / `M.D` / `M/D`; omit it to query tomorrow. Dates must be within today ~ today+14.

```bash
python3 scripts/query_transfer.py --from 密云 --to 锦州 --limit 10  # date omitted → tomorrow
python3 scripts/query_transfer.py --date 2026-02-25 --from 密云 --to 锦州 --limit 10
python3 scripts/query_transfer.py --date 2026-02-25 --from 密云 --to 锦州 --middle 承德南 --limit 10
```

### Output

- Prints a compact summary to stdout.
- Writes a machine-readable JSON to a cache file and prints the path.

## Notes for the agent

- Prefer using Chinese station names in user-facing prompts; the script will map to station codes.
- If the user provides an ambiguous station name, run station search via `scripts/stations.py --search` and ask a clarification.
- If the user **does not provide a date**, the scripts default to **tomorrow**; **explicitly remind** them that different dates may differ, then ask which date they want if they need accuracy.
- Keep results concise: list top trains (earliest few, shortest duration, or user-specified filters).

## Troubleshooting

- If station mapping is missing/outdated: run `python3 scripts/update_stations.py`.
- If you get **HTML** (mormhweb error page):
  - reduce frequency; wait 5–15 minutes before retry
  - try a different station combo (e.g. 锦州/锦州南/锦州北)
  - change outbound network (often the most effective)
