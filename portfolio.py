"""
portfolio.py — Portfolio management for StockPicker Web
"""

import json
import os
from datetime import date
import yfinance as yf

PORTFOLIO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "portfolio.json")


def load_portfolio():
    if not os.path.exists(PORTFOLIO_FILE):
        return {"holdings": [], "cash": 1000.0}
    with open(PORTFOLIO_FILE, "r") as f:
        data = json.load(f)
    if "cash" not in data:
        data["cash"] = 1000.0
    return data


def save_portfolio(data):
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_current_price(ticker):
    try:
        t = yf.Ticker(ticker.upper())
        hist = t.history(period="2d")
        if not hist.empty:
            return float(hist['Close'].iloc[-1])
    except Exception:
        pass
    return None


def portfolio_add(ticker, shares, buy_price, buy_date=None):
    """Add a position. Returns (success: bool, message: str)."""
    ticker = ticker.upper()
    shares = float(shares)
    buy_price = float(buy_price)
    buy_date = buy_date or str(date.today())

    data = load_portfolio()
    cost = shares * buy_price

    if cost > data["cash"]:
        return False, f"Insufficient cash! Available: ${data['cash']:.2f}, Cost: ${cost:.2f}"

    for h in data["holdings"]:
        if h["ticker"] == ticker:
            old_cost = h["shares"] * h["buy_price"]
            new_cost = shares * buy_price
            h["shares"] += shares
            h["buy_price"] = (old_cost + new_cost) / h["shares"]
            h["buy_date"] = buy_date
            data["cash"] -= cost
            save_portfolio(data)
            return True, f"Added {shares} more shares of {ticker} @ ${buy_price:.2f}. Total: {h['shares']} shares, Avg cost: ${h['buy_price']:.2f}. Cash: ${data['cash']:.2f}"

    data["holdings"].append({
        "ticker": ticker,
        "shares": shares,
        "buy_price": buy_price,
        "buy_date": buy_date
    })
    data["cash"] -= cost
    save_portfolio(data)
    return True, f"Added {shares} shares of {ticker} @ ${buy_price:.2f} (Cost: ${cost:.2f}). Cash: ${data['cash']:.2f}"


def portfolio_remove(ticker):
    """Remove/sell a position. Returns (success, message)."""
    ticker = ticker.upper()
    data = load_portfolio()

    removed = None
    for h in data["holdings"]:
        if h["ticker"] == ticker:
            removed = h
            break

    if not removed:
        return False, f"No position found for {ticker}"

    current_price = get_current_price(ticker) or removed["buy_price"]
    proceeds = removed["shares"] * current_price
    data["cash"] += proceeds
    data["holdings"] = [h for h in data["holdings"] if h["ticker"] != ticker]
    save_portfolio(data)

    gain = (current_price - removed["buy_price"]) * removed["shares"]
    gain_pct = ((current_price / removed["buy_price"]) - 1) * 100

    return True, f"Sold {removed['shares']} shares of {ticker} @ ${current_price:.2f}. Proceeds: ${proceeds:.2f}, P&L: ${gain:+.2f} ({gain_pct:+.1f}%). Cash: ${data['cash']:.2f}"


def portfolio_summary():
    """Get portfolio with current prices. Returns dict with holdings details and summary."""
    data = load_portfolio()
    holdings = data["holdings"]
    cash = data["cash"]

    enriched = []
    total_value = 0.0
    total_cost = 0.0

    for h in holdings:
        current_price = get_current_price(h["ticker"])
        stale = current_price is None
        if stale:
            current_price = h["buy_price"]

        cost_basis = h["shares"] * h["buy_price"]
        current_val = h["shares"] * current_price
        gain = current_val - cost_basis
        gain_pct = ((current_price / h["buy_price"]) - 1) * 100

        total_value += current_val
        total_cost += cost_basis

        enriched.append({
            "ticker": h["ticker"],
            "shares": h["shares"],
            "buy_price": round(h["buy_price"], 2),
            "current_price": round(current_price, 2),
            "stale": stale,
            "value": round(current_val, 2),
            "cost_basis": round(cost_basis, 2),
            "gain": round(gain, 2),
            "gain_pct": round(gain_pct, 1),
            "buy_date": h["buy_date"],
        })

    total_gain = total_value - total_cost
    total_gain_pct = ((total_value / total_cost) - 1) * 100 if total_cost > 0 else 0

    return {
        "holdings": enriched,
        "cash": round(cash, 2),
        "total_value": round(total_value, 2),
        "total_cost": round(total_cost, 2),
        "total_gain": round(total_gain, 2),
        "total_gain_pct": round(total_gain_pct, 1),
        "portfolio_total": round(total_value + cash, 2),
    }


def set_cash(amount):
    """Set the cash balance directly."""
    data = load_portfolio()
    data["cash"] = float(amount)
    save_portfolio(data)
    return True, f"Cash set to ${amount:.2f}"
