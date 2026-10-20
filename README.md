# Crypto Opportunity Radar (MVP)

A read-only crypto market scanner. It does not connect to wallets/exchanges, place orders, or promise returns.

## What it does
- Pulls listed coin market data from CoinGecko's public markets endpoint.
- Screens candidates with a transparent 100-point heuristic score.
- Shows live-data timestamp, score breakdown, risk flags, and purely mathematical 10x/20x/30x market-cap scenarios.
- Creates rule-based WATCH / ENTRY-SETUP / EXIT-WATCH labels from price history. These are research signals, not financial advice.
- Provides a small phone-friendly PWA dashboard.
- Supports twice-daily scans via an external scheduler (recommended) or manual refresh.

## Important limitations
- "All credible projects" cannot be exhaustively scanned. The MVP scans up to 250 listed assets exposed by the configured provider; unlisted tokens and many new DEX tokens are excluded.
- CoinGecko public API limits and fields can change. Missing fields are marked unavailable, not guessed.
- A score is a screening heuristic, not a calibrated probability of a 10x return.
- Market-cap multiplication assumes circulating supply and valuation multiples remain comparable. Real token unlocks, dilution, liquidity and price impact can make this wrong.
- Current version uses price/volume/market-cap signals only. It does not claim to audit contracts, verify team identity, or detect all scams.
- The API has no authentication. Keep it private or add authentication before public deployment.

## Data source
CoinGecko public API:
`https://api.coingecko.com/api/v3/coins/markets`
Price currency is GBP. Check CoinGecko's current terms, limits and API documentation before deployment. This app makes no guarantee of uninterrupted free API access.

## Run locally
Requires Python 3.11+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

Open `http://127.0.0.1:8000`. The first scan is triggered when you press **Scan now**. The dashboard itself does not contain hardcoded market prices.

## Twice-daily automation
For a hosted deployment, run a scheduler (cron/GitHub Actions/hosting cron) that calls:

`POST https://YOUR-HOST/api/scan`

twice daily, for example at 08:00 and 20:00 Europe/London. Use UTC scheduling with daylight-saving adjustments if your scheduler does not support IANA time zones. This MVP's scan endpoint performs a scan on demand; it does not keep a background process alive by itself.

Example crontab (UTC; adjust for BST/GMT):
```
0 7,19 * * * curl -fsS -X POST https://YOUR-HOST/api/scan
```

For phone notifications, add a push-notification service in a later version. PWA notifications are not reliably scheduled by a closed phone app alone.

## Install on Android
1. Deploy the app to a HTTPS host (Render, Fly.io, Railway, or your own server). Free tiers and API limits may change.
2. Open the HTTPS URL in Chrome on Android.
3. Chrome menu (⋮) → **Add to Home screen** or **Install app**.
4. The app is a PWA; it opens like a separate app, but the backend must remain online for fresh data.

For local network testing, open the host computer's LAN address from the phone; this may require firewall configuration. HTTPS is required for standard PWA install/offline features outside localhost.

## Scoring (heuristic, not predictive probability)
- Momentum (0–25): 7-day and 30-day price change, clipped to avoid extreme values dominating.
- Volume/liquidity (0–20): 24h volume relative to market cap and absolute liquidity proxy.
- Market-cap runway (0–20): smaller market caps score higher, with a hard penalty for missing cap.
- Volume confirmation (0–15): positive 24h volume change and 24h price move.
- Data quality (0–10): market cap, volume, supply and price fields present.
- Risk penalty (0 to -30): extreme 24h movement, low liquidity, very low market cap, or missing market cap.
The displayed score is not a probability. It can reward risky microcaps; read all flags.

## Signal rules
- WATCH: score >= 55 and required market fields available.
- ENTRY-SETUP: WATCH plus 7-day change positive and 24h volume / market cap >= 0.05. This is a candidate for manual review, not a buy instruction.
- EXIT-WATCH: an item saved to the watchlist has fallen 12% or more from its recorded reference price, or has a negative 7-day change below -15%. This is a review trigger, not an automatic sell instruction.
- The app does not calculate a guaranteed stop-loss or a reliable 10x probability. Use position limits and assume microcaps can go to zero.

## Next production steps
1. Persist scan snapshots and watchlist in a database.
2. Add token contract verification and chain-specific liquidity data from reputable sources.
3. Add backtesting with out-of-sample tests, fees, slippage, survivorship bias controls, and signal history.
4. Add authentication, rate limiting, and push notifications.
5. Package a native Android app (Kotlin/Compose) if desired.
