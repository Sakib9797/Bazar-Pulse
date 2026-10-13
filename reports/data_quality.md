# Data quality report

- Files downloaded: **1409**; parsed OK: **1408**; failed: **1**
- Price rows: **74,988** for **63** products, 2021-05-17 to 2026-10-13 (1405 report days)
- Products per report day: median 52, min 50
- Files whose repeated page header carries a different date: **5**
- Schema check on the full table: **pass**
- '1 week ago' cross-check (sampled weekly, last ~4 months): median mismatch 0.0% of products

## Files that failed to parse

- `data/raw/2023/2023-10-15_283f0a91.xlsx`: file contains only zero bytes (corrupt on TCB's server)

## Coverage

| Year | Report days |
|---|---|
| 2021 | 156 |
| 2022 | 64 |
| 2023 | 261 |
| 2024 | 329 |
| 2025 | 334 |
| 2026 | 261 |

Largest gaps between report days (TCB's archive has no files for these periods):

- 2022-08-22 to 2022-12-15: 115 days
- 2022-03-11 to 2022-04-12: 32 days
- 2022-07-21 to 2022-08-22: 32 days
