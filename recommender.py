"""
recommender.py — Buy/Sell recommendation logic for StockPicker Web
"""

import yfinance as yf
from screener import calculate_rsi, score_stock, ALL_TICKERS
from sentiment import get_sentiment_score
from portfolio import load_portfolio, get_current_price
import json
import os

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config():
    defaults = {"max_price": 100, "stop_loss_pct": 8, "budget": 1000}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            data = json.load(f)
        defaults.update(data)
    return defaults


def get_rsi_for_ticker(ticker):
    try:
        t = yf.Ticker(ticker.upper())
        hist = t.history(period="3mo")
        if hist.empty or len(hist) < 15:
            return None
        rsi_series = calculate_rsi(hist['Close'].dropna())
        return float(rsi_series.iloc[-1]) if not rsi_series.empty else None
    except Exception:
        return None


def run_recommendations():
    """Generate recommendations. Returns dict with sell_signals and buy_candidates."""
    config = load_config()
    stop_loss_pct = config["stop_loss_pct"]
    max_price = config["max_price"]

    data = load_portfolio()
    holdings = data["holdings"]

    # Check holdings for SELL signals
    sell_signals = []
    for h in holdings:
        ticker = h["ticker"]
        buy_price = h["buy_price"]
        current_price = get_current_price(ticker)

        if current_price is None:
            continue

        change_pct = ((current_price / buy_price) - 1) * 100
        rsi = get_rsi_for_ticker(ticker)
        sentiment = get_sentiment_score(ticker)

        reasons = []
        action = "HOLD"

        if change_pct <= -stop_loss_pct:
            action = "SELL"
            reasons.append(f"Stop-loss hit ({change_pct:.1f}%)")

        if rsi is not None and rsi > 70 and sentiment < -0.05:
            action = "SELL"
            reasons.append(f"RSI overbought ({rsi:.0f}) + negative sentiment")

        if rsi is not None and rsi > 75 and action != "SELL":
            action = "SELL"
            reasons.append(f"RSI very overbought ({rsi:.0f})")

        if action == "HOLD" and rsi is not None:
            if rsi < 50 and change_pct > 0:
                reasons.append("Momentum holding, RSI has room")
            elif sentiment > 0.1:
                reasons.append("Positive news sentiment")
            else:
                reasons.append("No strong sell signal")

        sell_signals.append({
            "ticker": ticker,
            "buy_price": round(buy_price, 2),
            "current_price": round(current_price, 2),
            "change_pct": round(change_pct, 1),
            "rsi": round(rsi, 1) if rsi is not None else None,
            "sentiment": round(sentiment, 2),
            "action": action,
            "reasons": reasons,
        })

    # Find BUY candidates
    buy_candidates = []
    for ticker in ALL_TICKERS:
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="1y")
            if hist.empty or len(hist) < 50:
                continue
            current_price = float(hist['Close'].iloc[-1])
            if current_price > max_price:
                continue
            score, signals, rsi_val = score_stock(hist)
            if score >= 60:
                sentiment = get_sentiment_score(ticker)
                is_buy = score >= 70 and sentiment > -0.1

                if is_buy:
                    action = "BUY"
                else:
                    action = "WATCH"

                top_signal = signals[1] if len(signals) > 1 else signals[0] if signals else ""

                buy_candidates.append({
                    "ticker": ticker,
                    "price": round(current_price, 2),
                    "score": score,
                    "sentiment": round(sentiment, 2),
                    "action": action,
                    "signal": top_signal,
                })
        except Exception:
            continue

    buy_candidates.sort(key=lambda x: x['score'], reverse=True)

    return {
        "sell_signals": sell_signals,
        "buy_candidates": buy_candidates[:15],
        "config": {"stop_loss_pct": stop_loss_pct, "max_price": max_price},
    }
