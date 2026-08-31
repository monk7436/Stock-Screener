"""
FastAPI Server & REST / SSE Endpoints for Stock Screener
"""

import json
import os
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from backend.universes.nse_tickers import NSE_UNIVERSES
from backend.universes.us_tickers import US_UNIVERSES
from backend.screener import ScreenerCriteria, stream_screener_scan, evaluate_stock_filter
from backend.data_fetcher import get_stock_historical_chart_data

app = FastAPI(
    title="Real-Time Stock Screener API",
    description="Stock screener for NSE (India) & NYSE/US markets with technical and fundamental filters",
    version="1.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")


@app.get("/api/universes")
async def get_universes():
    """Returns available market indices and presets."""
    return {
        "markets": {
            "nse": {
                "name": "Indian Markets (NSE)",
                "currency": "₹ (INR)",
                "presets": {
                    k: {"name": v["name"], "count": len(v["tickers"])}
                    for k, v in NSE_UNIVERSES.items()
                }
            },
            "us": {
                "name": "US Markets (NYSE / NASDAQ)",
                "currency": "$ (USD)",
                "presets": {
                    k: {"name": v["name"], "count": len(v["tickers"])}
                    for k, v in US_UNIVERSES.items()
                }
            }
        }
    }


def resolve_tickers_for_request(
    market: str,
    universe: str,
    custom_tickers: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Helper to resolve symbol metadata list based on user selection."""
    if custom_tickers and custom_tickers.strip():
        raw_list = [s.strip().upper() for s in custom_tickers.replace(";", ",").split(",") if s.strip()]
        result = []
        for sym in raw_list:
            # Auto-format NSE suffix if market is nse and no suffix provided
            if market == "nse" and not (sym.endswith(".NS") or sym.endswith(".BO")):
                clean_sym = f"{sym}.NS"
            else:
                clean_sym = sym
            result.append({"symbol": clean_sym, "name": clean_sym, "sector": "Custom"})
        return result

    if market == "nse":
        uni = NSE_UNIVERSES.get(universe, NSE_UNIVERSES["nifty_50"])
        return uni["tickers"]
    elif market == "us":
        uni = US_UNIVERSES.get(universe, US_UNIVERSES["sp_500_top"])
        return uni["tickers"]
    else:
        return NSE_UNIVERSES["nifty_50"]["tickers"]


@app.get("/api/scan/stream")
async def scan_stream(
    market: str = Query(default="nse", description="Market: nse or us"),
    universe: str = Query(default="nifty_50", description="Index universe"),
    custom_tickers: Optional[str] = Query(default=None, description="Comma-separated custom symbols"),
    max_pe: Optional[float] = Query(default=20.0),
    min_pe: Optional[float] = Query(default=0.0),
    include_no_pe: bool = Query(default=False),
    min_volume_ratio: float = Query(default=2.0),
    max_volume_ratio: Optional[float] = Query(default=None),
    min_rsi: float = Query(default=50.0),
    max_rsi: float = Query(default=100.0),
    min_price: Optional[float] = Query(default=None),
    max_price: Optional[float] = Query(default=None),
    vol_weight: float = Query(default=0.45),
    rsi_weight: float = Query(default=0.35),
    pe_weight: float = Query(default=0.20)
):
    """
    Server-Sent Events (SSE) endpoint providing real-time streaming updates during screener execution.
    """
    criteria = ScreenerCriteria(
        max_pe=max_pe,
        min_pe=min_pe,
        include_no_pe=include_no_pe,
        min_volume_ratio=min_volume_ratio,
        max_volume_ratio=max_volume_ratio,
        min_rsi=min_rsi,
        max_rsi=max_rsi,
        min_price=min_price,
        max_price=max_price,
        vol_weight=vol_weight,
        rsi_weight=rsi_weight,
        pe_weight=pe_weight
    )

    tickers_meta = resolve_tickers_for_request(market, universe, custom_tickers)

    async def event_generator():
        try:
            async for event in stream_screener_scan(tickers_meta, criteria, chunk_size=35):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            err_data = {"type": "error", "message": f"Scan failed: {str(e)}"}
            yield f"data: {json.dumps(err_data)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/api/stock/{ticker}/chart")
async def get_stock_chart(ticker: str, period: str = Query(default="6mo"), interval: str = Query(default="1d")):
    """
    Returns historical candlestick and RSI data for charting modal.
    """
    data = get_stock_historical_chart_data(ticker, period=period, interval=interval)
    if "error" in data:
        raise HTTPException(status_code=404, detail=data["error"])
    return data


# Mount static assets
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
async def read_index():
    """Serves the main frontend dashboard."""
    index_file = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Stock Screener API is running. Frontend index.html not found."}
