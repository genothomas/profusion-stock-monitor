# Profusion Stock Monitor

Watches product pages on `gb.profusion.uk`. Discord alert on OOS → in-stock transition. Runs daily on GitHub Actions.

## Secrets

- `DISCORD_WEBHOOK_URL`
- `PRODUCT_URLS` — comma-separated product URLs
- `ALERT_SKUS` (optional) — comma-separated SKU slugs to alert; empty = alert all

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
JITTER_SECONDS=0 PRODUCT_URLS="https://gb.profusion.uk/uk/ecx10p20-w6s" \
STATE_PATH="$PWD/state.json" .venv/bin/python scraper.py
```

`DEBUG_FORCE_IN_STOCK=<sku>` fakes in-stock for testing.

## Detect

- `Stock: N` text → in stock
- `/media/catalog/stock/.../stock-no_*.png` → OOS