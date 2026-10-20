from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import math

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

APP_DIR = Path(__file__).parent
API_URL = "https://api.coingecko.com/api/v3/coins/markets"
app = FastAPI(title="Crypto Opportunity Radar", version="0.1.0")
app.mount("/web", StaticFiles(directory=APP_DIR / "web"), name="web")

# In-memory cache only for MVP. Restarting the server clears it.
latest_scan: dict[str, Any] | None = None

def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))

def score_coin(c: dict[str, Any]) -> dict[str, Any]:
    """Transparent heuristic score, not a return forecast or probability."""
    mc = c.get("market_cap")
    vol = c.get("total_volume")
    p7 = c.get("price_change_percentage_7d_in_currency")
    p30 = c.get("price_change_percentage_30d_in_currency")
    p24 = c.get("price_change_percentage_24h")
    vchg = c.get("total_volume")  # Provider endpoint may not supply volume change.
    price = c.get("current_price")
    supply = c.get("circulating_supply")
    flags: list[str] = []
    parts: dict[str, float] = {}

    # Momentum 0–25; missing history does not get an invented value.
    if p7 is not None and p30 is not None:
        momentum = clamp(12 + 0.22 * clamp(float(p7), -40, 40)
                         + 0.08 * clamp(float(p30), -60, 60), 0, 25)
        parts["momentum"] = round(momentum, 1)
    else:
        parts["momentum"] = 0
        flags.append("Insufficient 7d/30d price history")

    # Liquidity/volume proxy 0–20.
    if mc and vol and mc > 0:
        ratio = float(vol) / float(mc)
        liquidity = clamp(20 * math.log10(1 + ratio * 100) / math.log10(101), 0, 20)
        parts["volume_liquidity"] = round(liquidity, 1)
        if vol < 100_000:
            flags.append("Low 24h trading volume")
        if ratio < 0.01:
            flags.append("Low volume relative to market cap")
    else:
        parts["volume_liquidity"] = 0
        flags.append("Market cap or volume unavailable")

    # Lower cap can mean more theoretical runway, but is not a quality signal.
    if mc and mc > 0:
        cap_score = clamp(20 * (math.log10(10_000_000_000) - math.log10(float(mc))) /
                          (math.log10(10_000_000_000) - math.log10(1_000_000)), 0, 20)
        parts["market_cap_runway"] = round(cap_score, 1)
        if mc < 5_000_000:
            flags.append("Microcap: extreme volatility/manipulation risk")
    else:
        parts["market_cap_runway"] = 0
        flags.append("Market cap unavailable; upside scenarios withheld")

    # Confirmation score: provider often lacks volume-change history; do not fake it.
    if p24 is not None:
        confirmation = clamp(7.5 + 0.25 * clamp(float(p24), -30, 30), 0, 15)
        parts["price_confirmation"] = round(confirmation, 1)
    else:
        parts["price_confirmation"] = 0
        flags.append("24h price change unavailable")

    # Data quality 0–10.
    fields = [mc, vol, price, supply]
    quality = 2.5 * sum(x is not None and x > 0 for x in fields)
    parts["data_quality"] = round(quality, 1)

    penalty = 0.0
    if p24 is not None and abs(float(p24)) > 35:
        penalty += 10
        flags.append("Extreme 24h move; spike/reversal risk")
    if mc and mc < 1_000_000:
        penalty += 10
        flags.append("Very small market cap")
    if not mc:
        penalty += 15
    if vol and vol < 25_000:
        penalty += 8
    parts["risk_penalty"] = -round(penalty, 1)

    total = round(clamp(sum(parts[k] for k in
        ["momentum", "volume_liquidity", "market_cap_runway",
         "price_confirmation", "data_quality"]) - penalty, 0, 100), 1)

    if not mc or not vol or not price:
        signal = "INSUFFICIENT DATA"
    elif total >= 55 and p7 is not None and float(p7) > 0 and float(vol) / float(mc) >= 0.05:
        signal = "ENTRY-SETUP"
    elif total >= 55:
        signal = "WATCH"
    else:
        signal = "NO SIGNAL"

    scenarios = None
    if mc and mc > 0:
        scenarios = {f"{x}x": round(float(mc) * x, 2) for x in (10, 20, 30)}

    return {
        "id": c.get("id"), "symbol": (c.get("symbol") or "").upper(),
        "name": c.get("name"), "price_gbp": price, "market_cap_gbp": mc,
        "volume_24h_gbp": vol, "change_24h_pct": p24,
        "change_7d_pct": p7, "change_30d_pct": p30,
        "circulating_supply": supply, "score": total, "score_parts": parts,
        "signal": signal, "risk_flags": sorted(set(flags)),
        "market_cap_scenarios_gbp": scenarios,
        "last_updated": c.get("last_updated"),
        "source": "CoinGecko public API"
    }

async def do_scan() -> dict[str, Any]:
    global latest_scan
    params = {
        "vs_currency": "gbp",
        "order": "volume_desc",
        "per_page": 250,
        "page": 1,
        "sparkline": "false",
        "price_change_percentage": "24h,7d,30d",
    }
    headers = {"accept": "application/json", "user-agent": "CryptoOpportunityRadar/0.1"}
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.get(API_URL, params=params, headers=headers)
            resp.raise_for_status()
            raw = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Market data unavailable: {type(e).__name__}. No signals generated.")
    items = [score_coin(c) for c in raw if isinstance(c, dict)]
    items.sort(key=lambda x: x["score"], reverse=True)
    latest_scan = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "CoinGecko public API",
        "currency": "GBP",
        "asset_count": len(items),
        "data_status": "LIVE RESPONSE RECEIVED",
        "method_note": "Scores are transparent heuristics, not probabilities or guarantees.",
        "assets": items,
    }
    return latest_scan

@app.get("/")
def index():
    return FileResponse(APP_DIR / "web" / "index.html")

@app.get("/api/health")
def health():
    return {"status": "ok", "latest_scan_at": latest_scan.get("generated_at") if latest_scan else None}

@app.get("/api/scan")
async def get_scan():
    if latest_scan is None:
        return {"data_status": "NO SCAN YET", "message": "Press Scan now to fetch current market data.", "assets": []}
    return latest_scan

@app.post("/api/scan")
async def post_scan():
    return await do_scan()
