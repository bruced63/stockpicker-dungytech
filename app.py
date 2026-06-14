#!/usr/bin/env python3
# StockPicker — stocks.dungytech.com

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from datetime import datetime
import json
import os
import threading

app = Flask(__name__)
app.secret_key = os.environ.get("SP_SECRET_KEY", os.urandom(24))

@app.context_processor
def inject_year():
    return {"current_year": datetime.utcnow().year}

DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(DIR, "config.json")
PORTFOLIO_FILE = os.path.join(DIR, "portfolio.json")

os.environ["SP_CONFIG_FILE"] = CONFIG_FILE
os.environ["SP_PORTFOLIO_FILE"] = PORTFOLIO_FILE


def load_config():
    defaults = {"max_price": 100, "stop_loss_pct": 8, "budget": 1000}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            data = json.load(f)
        defaults.update(data)
    return defaults


def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


# ── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    from portfolio import portfolio_summary
    summary = portfolio_summary()
    config = load_config()
    return render_template("dashboard.html", summary=summary, config=config)


@app.route("/portfolio")
def portfolio_page():
    from portfolio import portfolio_summary, load_portfolio
    summary = portfolio_summary()
    raw = load_portfolio()
    return render_template("portfolio.html", summary=summary, cash=raw["cash"])


@app.route("/portfolio/add", methods=["POST"])
def portfolio_add_route():
    from portfolio import portfolio_add
    ticker = request.form.get("ticker", "").strip()
    shares = request.form.get("shares", "").strip()
    price = request.form.get("price", "").strip()
    buy_date = request.form.get("buy_date", "").strip() or None

    if not ticker or not shares or not price:
        flash("All fields (ticker, shares, price) are required.", "danger")
        return redirect(url_for("portfolio_page"))

    try:
        success, msg = portfolio_add(ticker, float(shares), float(price), buy_date)
        flash(msg, "success" if success else "danger")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    return redirect(url_for("portfolio_page"))


@app.route("/portfolio/sell", methods=["POST"])
def portfolio_sell_route():
    from portfolio import portfolio_remove
    ticker = request.form.get("ticker", "").strip()
    if not ticker:
        flash("Ticker is required.", "danger")
        return redirect(url_for("portfolio_page"))
    success, msg = portfolio_remove(ticker)
    flash(msg, "success" if success else "danger")
    return redirect(url_for("portfolio_page"))


@app.route("/portfolio/set-cash", methods=["POST"])
def portfolio_set_cash_route():
    from portfolio import set_cash
    amount = request.form.get("amount", "").strip()
    if not amount:
        flash("Amount is required.", "danger")
        return redirect(url_for("portfolio_page"))
    try:
        success, msg = set_cash(float(amount))
        flash(msg, "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    return redirect(url_for("portfolio_page"))


# ── Screener ─────────────────────────────────────────────────────────────────

screener_results = {"status": "idle", "data": None, "error": None}
screener_lock = threading.Lock()


@app.route("/screener")
def screener_page():
    return render_template("screener.html", config=load_config())


@app.route("/api/screener/run", methods=["POST"])
def screener_run():
    global screener_results
    with screener_lock:
        if screener_results["status"] == "running":
            return jsonify({"status": "already_running"})
        screener_results = {"status": "running", "data": None, "error": None}

    max_price = float(request.json.get("max_price", 100))
    top_n = int(request.json.get("top_n", 15))

    def _run():
        global screener_results
        try:
            from screener import run_screener
            results = run_screener(max_price=max_price, top_n=top_n)
            with screener_lock:
                screener_results = {"status": "done", "data": results, "error": None}
        except Exception as e:
            with screener_lock:
                screener_results = {"status": "error", "data": None, "error": str(e)}

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/api/screener/status")
def screener_status():
    with screener_lock:
        return jsonify(screener_results)


# ── Sentiment ─────────────────────────────────────────────────────────────────

@app.route("/sentiment")
def sentiment_page():
    return render_template("sentiment.html")


@app.route("/api/sentiment", methods=["POST"])
def sentiment_api():
    ticker = request.json.get("ticker", "").strip()
    if not ticker:
        return jsonify({"error": "Ticker required"}), 400
    from sentiment import analyze_sentiment
    return jsonify(analyze_sentiment(ticker))


# ── Recommendations ───────────────────────────────────────────────────────────

recommend_results = {"status": "idle", "data": None, "error": None}
recommend_lock = threading.Lock()


@app.route("/recommendations")
def recommendations_page():
    return render_template("recommendations.html", config=load_config())


@app.route("/api/recommendations/run", methods=["POST"])
def recommendations_run():
    global recommend_results
    with recommend_lock:
        if recommend_results["status"] == "running":
            return jsonify({"status": "already_running"})
        recommend_results = {"status": "running", "data": None, "error": None}

    def _run():
        global recommend_results
        try:
            from recommender import run_recommendations
            results = run_recommendations()
            with recommend_lock:
                recommend_results = {"status": "done", "data": results, "error": None}
        except Exception as e:
            with recommend_lock:
                recommend_results = {"status": "error", "data": None, "error": str(e)}

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/api/recommendations/status")
def recommendations_status():
    with recommend_lock:
        return jsonify(recommend_results)


# ── Settings ──────────────────────────────────────────────────────────────────

@app.route("/settings")
def settings_page():
    return render_template("settings.html", config=load_config())


@app.route("/settings/save", methods=["POST"])
def settings_save():
    try:
        config = {
            "max_price": float(request.form.get("max_price", 100)),
            "stop_loss_pct": float(request.form.get("stop_loss_pct", 8)),
            "budget": float(request.form.get("budget", 1000)),
        }
        save_config(config)
        flash("Settings saved!", "success")
    except Exception as e:
        flash(f"Error saving settings: {e}", "danger")
    return redirect(url_for("settings_page"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5002, debug=False)
