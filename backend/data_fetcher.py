"""
Data Fetcher and Ingestion Engine
Handles batch downloading from yfinance, rate limit throttling, multi-level caching, and fast fundamental extraction.
"""

import time
import logging
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import yfinance as yf

from backend.indicators import calculate_technical_summary, compute_rank_score

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DataFetcher")

# In-memory TTL Caches
# Key: ticker -> {"data": dict, "timestamp": float}
FUNDAMENTALS_CACHE: Dict[str, Dict[str, Any]] = {}
CANDLES_CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 900  # 15 minutes


def get_cached_fundamentals(ticker: str) -> Optional[Dict[str, Any]]:
    cached = FUNDAMENTALS_CACHE.get(ticker)
    if cached and (time.time() - cached["timestamp"] < CACHE_TTL_SECONDS):
        return cached["data"]
    return None


def set_cached_fundamentals(ticker: str, data: Dict[str, Any]):
    FUNDAMENTALS_CACHE[ticker] = {
        "data": data,
        "timestamp": time.time()
    }


def fetch_single_fundamental(ticker: str) -> Dict[str, Any]:
    """
    Fetches fundamental metrics (P/E, Market Cap, 52W range) for a single ticker.
    Uses yfinance fast_info and info with fallback.
    """
    cached = get_cached_fundamentals(ticker)
    if cached:
        return cached

    result = {
        "trailing_pe": None,
        "forward_pe": None,
        "market_cap": None,
        "currency": "INR" if ticker.endswith(".NS") or ticker.endswith(".BO") else "USD",
        "short_name": ticker,
        "sector": "Unknown",
        "industry": "Unknown"
    }

    try:
        t = yf.Ticker(ticker)
        # fast_info is lightweight and fast
        try:
            fast = getattr(t, "fast_info", None)
            if fast:
                result["market_cap"] = getattr(fast, "market_cap", None)
                result["currency"] = getattr(fast, "currency", result["currency"])
        except Exception:
            pass

        # info contains trailingPE / forwardPE / sector
        try:
            info = t.info
            if info:
                pe = info.get("trailingPE") or info.get("forwardPE")
                if pe is not None and not (isinstance(pe, float) and pd.isna(pe)):
                    result["trailing_pe"] = round(float(pe), 2)
                result["forward_pe"] = info.get("forwardPE")
                if result["market_cap"] is None:
                    result["market_cap"] = info.get("marketCap")
                result["short_name"] = info.get("shortName") or info.get("longName") or ticker
                result["sector"] = info.get("sector") or result["sector"]
                result["industry"] = info.get("industry") or result["industry"]
        except Exception as e:
            logger.debug(f"Could not retrieve full info for {ticker}: {e}")

    except Exception as e:
        logger.warning(f"Error fetching fundamentals for {ticker}: {e}")

    set_cached_fundamentals(ticker, result)
    return result


def fetch_fundamentals_batch(tickers: List[str], max_workers: int = 10) -> Dict[str, Dict[str, Any]]:
    """
    Fetches fundamentals concurrently across tickers using a thread pool.
    """
    results = {}
    tickers_to_fetch = []

    for sym in tickers:
        cached = get_cached_fundamentals(sym)
        if cached:
            results[sym] = cached
        else:
            tickers_to_fetch.append(sym)

    if tickers_to_fetch:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_sym = {executor.submit(fetch_single_fundamental, sym): sym for sym in tickers_to_fetch}
            for future in as_completed(future_to_sym):
                sym = future_to_sym[future]
                try:
                    results[sym] = future.result()
                except Exception as e:
                    logger.warning(f"Thread error fetching {sym}: {e}")
                    results[sym] = {
                        "trailing_pe": None,
                        "forward_pe": None,
                        "market_cap": None,
                        "currency": "INR" if sym.endswith(".NS") else "USD",
                        "short_name": sym,
                        "sector": "Unknown"
                    }
    return results


def download_candles_chunk(tickers: List[str], period: str = "2mo", interval: str = "1d") -> Dict[str, pd.DataFrame]:
    """
    Downloads historical candles for a chunk of tickers in a single batch request.
    Handles MultiIndex columns returned by yfinance.
    """
    if not tickers:
        return {}
    
    try:
        data = yf.download(
            tickers=tickers,
            period=period,
            interval=interval,
            group_by="ticker",
            threads=True,
            progress=False,
            auto_adjust=True
        )
        
        results: Dict[str, pd.DataFrame] = {}
        
        if len(tickers) == 1:
            sym = tickers[0]
            if isinstance(data, pd.DataFrame) and not data.empty:
                results[sym] = data
            return results

        # Multi-ticker download returns MultiIndex columns or level 0 tickers
        if isinstance(data.columns, pd.MultiIndex):
            # level 0 can be tickers or metrics
            levels = data.columns.levels
            if len(levels) > 0:
                first_level_items = set(data.columns.get_level_values(0))
                for sym in tickers:
                    if sym in first_level_items:
                        try:
                            df_sym = data[sym].dropna(how="all")
                            if not df_sym.empty:
                                results[sym] = df_sym
                        except Exception:
                            pass
        else:
            if len(tickers) == 1 and not data.empty:
                results[tickers[0]] = data

        return results

    except Exception as e:
        logger.error(f"Error downloading batch candles for {len(tickers)} tickers: {e}")
        return {}


def get_stock_historical_chart_data(ticker: str, period: str = "6mo", interval: str = "1d") -> Dict[str, Any]:
    """
    Returns historical candlestick & RSI series for interactive UI modal charts.
    """
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period, interval=interval, auto_adjust=True)
        if df.empty:
            return {"error": f"No historical data for {ticker}"}
        df = df.dropna(subset=["Close"])
        if df.empty:
            return {"error": f"No historical data for {ticker}"}

        df = df.reset_index()
        # Date string formatting
        date_col = "Date" if "Date" in df.columns else "Datetime"
        
        records = []
        close_prices = []
        
        for _, row in df.iterrows():
            d_val = row[date_col]
            d_str = d_val.strftime("%Y-%m-%d") if hasattr(d_val, "strftime") else str(d_val)[:10]
            c_val = round(float(row["Close"]), 2) if not pd.isna(row["Close"]) else None
            if c_val is None:
                continue
            o_val = round(float(row["Open"]), 2) if not pd.isna(row["Open"]) else c_val
            h_val = round(float(row["High"]), 2) if not pd.isna(row["High"]) else c_val
            l_val = round(float(row["Low"]), 2) if not pd.isna(row["Low"]) else c_val
            v_val = int(row["Volume"]) if not pd.isna(row["Volume"]) else 0

            close_prices.append(c_val)
            records.append({
                "date": d_str,
                "open": o_val,
                "high": h_val,
                "low": l_val,
                "close": c_val,
                "volume": v_val
            })

        # Calculate historical RSI series
        close_series = df["Close"]
        rsi_series = []
        if len(close_series) >= 15:
            delta = close_series.diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.ewm(alpha=1.0 / 14, min_periods=14, adjust=False).mean()
            avg_loss = loss.ewm(alpha=1.0 / 14, min_periods=14, adjust=False).mean()
            rs = avg_gain / avg_loss
            rsi_vals = 100.0 - (100.0 / (1.0 + rs))
            for v in rsi_vals:
                rsi_series.append(round(float(v), 2) if not pd.isna(v) else None)
        else:
            rsi_series = [None] * len(records)

        for i, rec in enumerate(records):
            rec["rsi"] = rsi_series[i] if i < len(rsi_series) else None

        fundamentals = fetch_single_fundamental(ticker)

        return {
            "ticker": ticker,
            "name": fundamentals.get("short_name", ticker),
            "currency": fundamentals.get("currency", "INR"),
            "candle_data": records,
            "fundamentals": fundamentals
        }
    except Exception as e:
        logger.error(f"Error fetching chart data for {ticker}: {e}")
        return {"error": str(e)}
