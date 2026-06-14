"""
screener.py — Stock screening logic for StockPicker Web
"""

import yfinance as yf
import pandas as pd

SP500_SAMPLE = [
    "AAPL", "MSFT", "AMZN", "GOOGL", "META", "BRK-B", "UNH", "JNJ", "XOM",
    "JPM", "V", "PG", "MA", "AVGO", "CVX", "MRK", "PEP", "ABBV", "KO",
    "COST", "WMT", "MCD", "BAC", "TMO", "CSCO", "ABT", "DHR", "ACN", "LIN",
    "NEE", "NKE", "TXN", "PM", "HON", "UPS", "AMGN", "LOW", "QCOM", "SBUX",
    "IBM", "GE", "CAT", "SPGI", "BLK", "MDLZ", "GS", "ISRG", "AXP", "DE",
    "EL", "PLD", "SO", "DUK", "CL", "CME", "SHW", "ZTS", "MMC", "CI",
    "F", "GM", "USB", "WFC", "C", "MS", "AIG", "MET", "PRU", "TRV"
]

NASDAQ100_SAMPLE = [
    "NVDA", "TSLA", "ADBE", "NFLX", "PYPL", "INTC", "CMCSA", "PEP", "TMUS",
    "AMGN", "GILD", "REGN", "BIIB", "VRTX", "ILMN", "IDXX", "ALGN", "DXCM",
    "MRNA", "TEAM", "ZM", "DOCU", "OKTA", "CRWD", "SNOW", "DDOG", "NET",
    "ABNB", "DASH", "RBLX", "UBER", "LYFT", "PINS", "SNAP", "TWTR", "SQ",
    "ROKU", "SPOT", "NUAN", "BIDU", "JD", "PDD", "BABA", "NTES"
]

ALL_TICKERS = list(set(SP500_SAMPLE + NASDAQ100_SAMPLE))


def calculate_rsi(prices, period=14):
    """Calculate RSI for a price series."""
    delta = prices.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def score_stock(data, info=None):
    """Score a stock 0-100 based on technical signals. Returns (score, signals, rsi_value)."""
    score = 50
    signals = []
    rsi_value = None

    try:
        close = data['Close'].dropna()
        volume = data['Volume'].dropna()

        if len(close) < 50:
            return 0, ["Not enough data"], None

        # RSI
        rsi_series = calculate_rsi(close)
        rsi = float(rsi_series.iloc[-1]) if not rsi_series.empty else None
        rsi_value = rsi

        if rsi is not None:
            if rsi < 30:
                score += 20
                signals.append(f"RSI {rsi:.1f} (oversold ↑)")
            elif rsi < 45:
                score += 10
                signals.append(f"RSI {rsi:.1f} (mildly oversold)")
            elif rsi > 70:
                score -= 20
                signals.append(f"RSI {rsi:.1f} (overbought ↓)")
            elif rsi > 60:
                score -= 5
                signals.append(f"RSI {rsi:.1f} (mildly overbought)")
            else:
                signals.append(f"RSI {rsi:.1f} (neutral)")

        # Moving Averages
        ma50 = float(close.rolling(50).mean().iloc[-1])
        current_price = float(close.iloc[-1])

        if len(close) >= 200:
            ma200 = float(close.rolling(200).mean().iloc[-1])
            if ma50 > ma200:
                score += 15
                signals.append("Golden cross (50MA > 200MA ↑)")
            else:
                score -= 15
                signals.append("Death cross (50MA < 200MA ↓)")
        else:
            signals.append("200MA unavailable")

        if current_price > ma50 * 1.05:
            score += 5
            signals.append("Price well above 50MA")
        elif current_price < ma50 * 0.95:
            score += 5
            signals.append("Price below 50MA (potential rebound)")

        # Volume Spike
        vol_30d_avg = float(volume.tail(30).mean())
        vol_today = float(volume.iloc[-1])
        vol_ratio = vol_today / vol_30d_avg if vol_30d_avg > 0 else 1.0

        if vol_ratio > 2.0:
            score += 10
            signals.append(f"Volume spike {vol_ratio:.1f}x avg ↑")
        elif vol_ratio > 1.5:
            score += 5
            signals.append(f"Volume elevated {vol_ratio:.1f}x avg")
        else:
            signals.append(f"Volume normal {vol_ratio:.1f}x avg")

        # 52-week position
        high_52w = float(close.tail(252).max())
        low_52w = float(close.tail(252).min())
        range_52w = high_52w - low_52w
        pos_52w = (current_price - low_52w) / range_52w if range_52w > 0 else 0.5

        if pos_52w < 0.25:
            score += 10
            signals.append(f"Near 52-wk low ({pos_52w*100:.0f}% of range ↑)")
        elif pos_52w > 0.85:
            score -= 5
            signals.append(f"Near 52-wk high ({pos_52w*100:.0f}% of range)")
        else:
            signals.append(f"52-wk position: {pos_52w*100:.0f}%")

        score = max(0, min(100, score))
        return round(score), signals, rsi_value

    except Exception as e:
        return 0, [f"Error: {e}"], None


def run_screener(max_price=100, top_n=10):
    """Run the stock screener. Returns list of result dicts."""
    results = []

    for ticker in ALL_TICKERS:
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="1y")

            if hist.empty or len(hist) < 30:
                continue

            current_price = float(hist['Close'].iloc[-1])
            if current_price > max_price:
                continue

            score, signals, rsi_value = score_stock(hist)

            results.append({
                "ticker": ticker,
                "price": round(current_price, 2),
                "score": score,
                "signals": signals,
                "rsi": round(rsi_value, 1) if rsi_value is not None else None,
            })
        except Exception:
            continue

    results.sort(key=lambda x: x['score'], reverse=True)
    return results[:top_n]
