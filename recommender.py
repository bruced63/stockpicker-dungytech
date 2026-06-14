# recommender.py — Buy/Sell recommendation logic for StockPicker Web

import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
from screener import calculate_rsi, score_stock, ALL_TICKERS, batch_download
from sentiment import get_sentiment_score
from portfolio import load_portfolio
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


def _fetch_sentiments(tickers, max_workers=8):
    """Fetch sentiment scores for multiple tickers in parallel."""
    if not tickers:
        return {}
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        future_to_ticker = {ex.submit(get_sentiment_score, t): t for t in tickers}
        for future in as_completed(future_to_ticker):
            t = future_to_ticker[future]
            try:
                results[t] = future.result()
            except Exception:
                results[t] = 0.0
    return results


def run_recommendations():
    """Generate recommendations. Returns dict with sell_signals and buy_candidates."""
    config = load_config()
    stop_loss_pct = config["stop_loss_pct"]
    max_price = config["max_price"]

    portfolio = load_portfolio()
    holdings = portfolio["holdings"]
    holding_tickers = [h["ticker"] for h in holdings]

    # One batch download covers both holdings analysis and BUY scan
    all_tickers = list(set(ALL_TICKERS + holding_tickers))
    hist_map = batch_download(all_tickers, period="1y")

    # ── Analyse holdings for SELL signals (technicals only, no network calls) ──
    pending_sell = []  # (holding_dict, current_price, rsi)
    for h in holdings:
        ticker = h["ticker"]
        hist = hist_map.get(ticker)
        if hist is None or len(hist) < 15:
            continue
        current_price = float(hist['Close'].iloc[-1])
        rsi_series = calculate_rsi(hist['Close'].dropna())
        rsi = float(rsi_series.iloc[-1]) if not rsi_series.empty else None
        pending_sell.append((h, current_price, rsi))

    # ── Score all BUY candidates from batch data (no network calls) ──
    pending_buy = []  # (ticker, price, score, signals, rsi_val)
    for ticker in ALL_TICKERS:
        hist = hist_map.get(ticker)
        if hist is None or len(hist) < 50:
            continue
        try:
            current_price = float(hist['Close'].iloc[-1])
            if current_price > max_price:
                continue
            score, signals, rsi_val = score_stock(hist)
            if score >= 60:
                pending_buy.append((ticker, current_price, score, signals, rsi_val))
        except Exception:
            continue

    # ── Fetch all sentiment in parallel (one round-trip per ticker, concurrent) ──
    sentiment_tickers = list({t for t, *_ in pending_buy} | set(holding_tickers))
    sentiment_map = _fetch_sentiments(sentiment_tickers)

    # ── Build sell signals ──
    sell_signals = []
    for h, current_price, rsi in pending_sell:
        ticker = h["ticker"]
        buy_price = h["buy_price"]
        change_pct = ((current_price / buy_price) - 1) * 100
        sentiment = sentiment_map.get(ticker, 0.0)

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

    # ── Build buy candidates ──
    buy_candidates = []
    for ticker, price, score, signals, rsi_val in pending_buy:
        sentiment = sentiment_map.get(ticker, 0.0)
        action = "BUY" if score >= 70 and sentiment > -0.1 else "WATCH"
        top_signal = signals[1] if len(signals) > 1 else signals[0] if signals else ""
        buy_candidates.append({
            "ticker": ticker,
            "price": round(price, 2),
            "score": score,
            "sentiment": round(sentiment, 2),
            "action": action,
            "signal": top_signal,
        })

    buy_candidates.sort(key=lambda x: x['score'], reverse=True)

    return {
        "sell_signals": sell_signals,
        "buy_candidates": buy_candidates[:15],
        "config": {"stop_loss_pct": stop_loss_pct, "max_price": max_price},
    }
