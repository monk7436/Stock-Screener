"""
Technical and Fundamental Indicator Calculations
Implements RSI (Wilder's smoothing), 20-day Volume Spike Ratio, Moving Averages, and Multi-factor Ranking.
"""

from typing import Dict, Any, Optional, Tuple
import numpy as np
import pandas as pd


def calculate_rsi(series: pd.Series, period: int = 14) -> Optional[float]:
    """
    Computes 14-period Relative Strength Index (RSI) using Wilder's Exponential Smoothing.
    """
    if series is None or len(series) < period + 1:
        return None
    
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    # Wilder's smoothing (alpha = 1 / period)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    
    last_gain = avg_gain.iloc[-1]
    last_loss = avg_loss.iloc[-1]
    
    if pd.isna(last_gain) or pd.isna(last_loss):
        return None
    
    if last_loss == 0:
        return 100.0 if last_gain > 0 else 50.0
    
    rs = last_gain / last_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return round(float(rsi), 2)


def calculate_volume_spike(volume_series: pd.Series, window: int = 20) -> Tuple[int, int, float]:
    """
    Calculates current daily volume, 20-day rolling average volume, and volume spike ratio.
    Returns: (current_volume, avg_20d_volume, volume_ratio)
    """
    if volume_series is None or len(volume_series) == 0:
        return 0, 0, 0.0
    
    current_volume = int(volume_series.iloc[-1]) if not pd.isna(volume_series.iloc[-1]) else 0
    
    # Exclude the current day to compute true historical 20-day baseline average
    hist_series = volume_series.iloc[:-1] if len(volume_series) > 1 else volume_series
    avg_volume = int(hist_series.tail(window).mean()) if len(hist_series) > 0 else current_volume
    
    if avg_volume <= 0:
        ratio = 1.0 if current_volume > 0 else 0.0
    else:
        ratio = round(float(current_volume / avg_volume), 2)
        
    return current_volume, avg_volume, ratio


def calculate_technical_summary(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Extracts complete technical snapshot from OHLCV dataframe.
    """
    if df is None or len(df) < 5:
        return {
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
    
    close = df["Close"].dropna()
    volume = df["Volume"].dropna()
    high = df["High"].dropna() if "High" in df else close
    low = df["Low"].dropna() if "Low" in df else close
    
    if len(close) < 2:
        return {}

    current_price = round(float(close.iloc[-1]), 2)
    prev_close = float(close.iloc[-2]) if len(close) >= 2 else current_price
    change_1d_pct = round(((current_price - prev_close) / prev_close) * 100.0, 2) if prev_close > 0 else 0.0
    
    rsi = calculate_rsi(close, period=14)
    current_vol, avg_vol_20d, vol_ratio = calculate_volume_spike(volume, window=20)
    
    high_52w = round(float(high.max()), 2) if len(high) > 0 else current_price
    low_52w = round(float(low.min()), 2) if len(low) > 0 else current_price
    
    sma_20 = round(float(close.tail(20).mean()), 2) if len(close) >= 20 else None
    sma_50 = round(float(close.tail(50).mean()), 2) if len(close) >= 50 else None
    sma_200 = round(float(close.tail(200).mean()), 2) if len(close) >= 200 else None

    return {
        "current_price": current_price,
        "change_1d_pct": change_1d_pct,
        "rsi": rsi,
        "current_volume": current_vol,
        "avg_volume_20d": avg_vol_20d,
        "volume_ratio": vol_ratio,
        "high_52w": high_52w,
        "low_52w": low_52w,
        "sma_20": sma_20,
        "sma_50": sma_50,
        "sma_200": sma_200,
    }


def compute_rank_score(
    volume_ratio: float,
    rsi: Optional[float],
    pe_ratio: Optional[float],
    vol_weight: float = 0.45,
    rsi_weight: float = 0.35,
    pe_weight: float = 0.20
) -> float:
    """
    Computes a composite score (0-100) based on weighted multi-factor ranking:
    - Volume Spike (45% default)
    - RSI Momentum (35% default)
    - Valuation / PE (20% default)
    """
    # 1. Volume Score: Scale 1.0x - 5.0x spike to 0 - 100
    if volume_ratio <= 0:
        vol_score = 0.0
    else:
        # 1.0x = 20pts, 2.0x = 50pts, 4.0x+ = 100pts
        vol_score = min(max((volume_ratio / 4.0) * 100.0, 0.0), 100.0)
    
    # 2. RSI Score: RSI 50-80 indicates bullish momentum without extreme saturation
    if rsi is None or np.isnan(rsi):
        rsi_score = 50.0
    else:
        # RSI 50 -> 50pts, RSI 70 -> 90pts, RSI 80 -> 100pts
        if rsi < 30:
            rsi_score = max((rsi / 30.0) * 25.0, 0.0)
        elif rsi < 50:
            rsi_score = 25.0 + ((rsi - 30.0) / 20.0) * 25.0
        elif rsi <= 80:
            rsi_score = 50.0 + ((rsi - 50.0) / 30.0) * 50.0
        else:
            # Slightly penalized if heavily overbought > 85
            rsi_score = max(100.0 - (rsi - 80.0) * 2.0, 70.0)
            
    # 3. P/E Score: Lower positive P/E indicates better value
    if pe_ratio is None or np.isnan(pe_ratio) or pe_ratio <= 0:
        # Non-profitable or missing PE gets neutral score
        pe_score = 30.0
    else:
        # PE < 10 -> 95-100pts, PE 20 -> 60pts, PE 40 -> 20pts, PE > 60 -> 0pts
        if pe_ratio <= 10:
            pe_score = 100.0 - (pe_ratio / 10.0) * 10.0
        elif pe_ratio <= 20:
            pe_score = 90.0 - ((pe_ratio - 10.0) / 10.0) * 30.0
        elif pe_ratio <= 40:
            pe_score = 60.0 - ((pe_ratio - 20.0) / 20.0) * 40.0
        else:
            pe_score = max(20.0 - ((pe_ratio - 40.0) / 40.0) * 20.0, 0.0)
            
    total_score = (vol_score * vol_weight) + (rsi_score * rsi_weight) + (pe_score * pe_weight)
    return round(float(total_score), 1)
