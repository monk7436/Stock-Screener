"""
Core Screener Engine
Coordinates universe scans, applies indicator thresholds, computes ranking, and yields streaming progress.
"""

import time
import asyncio
from typing import List, Dict, Any, Optional, AsyncGenerator
from pydantic import BaseModel, Field

from backend.indicators import calculate_technical_summary, compute_rank_score
from backend.data_fetcher import download_candles_chunk, fetch_fundamentals_batch


class ScreenerCriteria(BaseModel):
    max_pe: Optional[float] = Field(default=20.0, description="Max Price-to-Earnings ratio")
    min_pe: Optional[float] = Field(default=0.0, description="Min Price-to-Earnings ratio")
    include_no_pe: bool = Field(default=False, description="Include loss-making or missing PE companies")
    min_volume_ratio: float = Field(default=2.0, description="Min volume spike compared to 20-day avg (e.g. 2.0x)")
    max_volume_ratio: Optional[float] = Field(default=None, description="Max volume spike ratio")
    min_rsi: float = Field(default=50.0, description="Min 14-day RSI (e.g. 50.0)")
    max_rsi: float = Field(default=100.0, description="Max 14-day RSI (e.g. 100.0)")
    min_price: Optional[float] = Field(default=None, description="Min stock price")
    max_price: Optional[float] = Field(default=None, description="Max stock price")
    vol_weight: float = Field(default=0.45, description="Volume spike ranking weight")
    rsi_weight: float = Field(default=0.35, description="RSI ranking weight")
    pe_weight: float = Field(default=0.20, description="PE valuation ranking weight")


def evaluate_stock_filter(item: Dict[str, Any], criteria: ScreenerCriteria) -> bool:
    """
    Evaluates whether a processed stock item meets the filter criteria.
    """
    # 1. Volume Ratio Filter
    vol_ratio = item.get("volume_ratio", 0.0)
    if vol_ratio < criteria.min_volume_ratio:
        return False
    if criteria.max_volume_ratio is not None and vol_ratio > criteria.max_volume_ratio:
        return False

    # 2. RSI Filter
    rsi = item.get("rsi")
    if rsi is None:
        return False
    if rsi < criteria.min_rsi or rsi > criteria.max_rsi:
        return False

    # 3. P/E Ratio Filter
    pe = item.get("trailing_pe")
    if pe is None or pe <= 0:
        if not criteria.include_no_pe:
            return False
    else:
        if criteria.min_pe is not None and pe < criteria.min_pe:
            return False
        if criteria.max_pe is not None and pe > criteria.max_pe:
            return False

    # 4. Price Filter
    price = item.get("current_price", 0.0)
    if criteria.min_price is not None and price < criteria.min_price:
        return False
    if criteria.max_price is not None and price > criteria.max_price:
        return False

    return True


async def stream_screener_scan(
    tickers_meta: List[Dict[str, Any]],
    criteria: ScreenerCriteria,
    chunk_size: int = 40
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Executes a scan over a list of ticker metadata objects and yields SSE progress events.
    """
    total = len(tickers_meta)
    scanned_count = 0
    all_processed: List[Dict[str, Any]] = []
    matched_results: List[Dict[str, Any]] = []

    # Map symbol -> meta (name, sector)
    meta_lookup = {item["symbol"]: item for item in tickers_meta}
    symbols = [item["symbol"] for item in tickers_meta]

    yield {
        "type": "start",
        "total": total,
        "scanned": 0,
        "matched_count": 0,
        "message": f"Starting scan for {total} stocks..."
    }

    # Process in chunks
    for i in range(0, total, chunk_size):
        chunk_symbols = symbols[i : i + chunk_size]
        
        # 1. Download OHLCV candles
        candles_dict = await asyncio.to_thread(download_candles_chunk, chunk_symbols, "2mo", "1d")
        
        # 2. Fetch fundamentals in parallel
        fundamentals_dict = await asyncio.to_thread(fetch_fundamentals_batch, chunk_symbols, 10)

        # 3. Process each ticker in chunk
        for sym in chunk_symbols:
            scanned_count += 1
            meta = meta_lookup.get(sym, {})
            df = candles_dict.get(sym)
            fund = fundamentals_dict.get(sym, {})

            if df is not None and not df.empty:
                tech = calculate_technical_summary(df)
            else:
                tech = {
                    "current_price": 0.0,
                    "change_1d_pct": 0.0,
                    "rsi": None,
                    "current_volume": 0,
                    "avg_volume_20d": 0,
                    "volume_ratio": 0.0,
                    "high_52w": 0.0,
                    "low_52w": 0.0,
                    "sma_20": None,
                    "sma_50": None,
                    "sma_200": None,
                }

            trailing_pe = fund.get("trailing_pe")
            market_cap = fund.get("market_cap")
            company_name = fund.get("short_name") or meta.get("name", sym)
            sector = fund.get("sector") if fund.get("sector") != "Unknown" else meta.get("sector", "General")
            currency = fund.get("currency", "INR" if sym.endswith(".NS") else "USD")

            rank_score = compute_rank_score(
                volume_ratio=tech.get("volume_ratio", 0.0),
                rsi=tech.get("rsi"),
                pe_ratio=trailing_pe,
                vol_weight=criteria.vol_weight,
                rsi_weight=criteria.rsi_weight,
                pe_weight=criteria.pe_weight
            )

            stock_data = {
                "symbol": sym,
                "name": company_name,
                "sector": sector,
                "currency": currency,
                "current_price": tech.get("current_price", 0.0),
                "change_1d_pct": tech.get("change_1d_pct", 0.0),
                "trailing_pe": trailing_pe,
                "volume_ratio": tech.get("volume_ratio", 0.0),
                "current_volume": tech.get("current_volume", 0),
                "avg_volume_20d": tech.get("avg_volume_20d", 0),
                "rsi": tech.get("rsi"),
                "high_52w": tech.get("high_52w", 0.0),
                "low_52w": tech.get("low_52w", 0.0),
                "sma_20": tech.get("sma_20"),
                "sma_50": tech.get("sma_50"),
                "sma_200": tech.get("sma_200"),
                "market_cap": market_cap,
                "rank_score": rank_score,
            }

            all_processed.append(stock_data)

            # Check filter criteria
            if evaluate_stock_filter(stock_data, criteria):
                matched_results.append(stock_data)

        # Sort currently matched by rank score
        matched_results.sort(key=lambda x: x.get("rank_score", 0.0), reverse=True)
        for idx, item in enumerate(matched_results):
            item["rank"] = idx + 1

        # Yield progress update per chunk
        yield {
            "type": "progress",
            "total": total,
            "scanned": scanned_count,
            "matched_count": len(matched_results),
            "matches": matched_results,
            "all_scanned": all_processed,
            "message": f"Scanned {scanned_count}/{total} stocks... ({len(matched_results)} matches)"
        }
        
        # Adaptive yield to keep event loop snappy
        await asyncio.sleep(0.05)

    # Final Complete Event
    matched_results.sort(key=lambda x: x.get("rank_score", 0.0), reverse=True)
    for idx, item in enumerate(matched_results):
        item["rank"] = idx + 1

    all_processed.sort(key=lambda x: x.get("rank_score", 0.0), reverse=True)

    yield {
        "type": "complete",
        "total": total,
        "scanned": total,
        "matched_count": len(matched_results),
        "matches": matched_results,
        "all_scanned": all_processed,
        "message": f"Scan completed! {len(matched_results)} stocks matched your filter criteria."
    }
