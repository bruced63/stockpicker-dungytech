# app.py — StockPicker · stocks.dungytech.com · Dungy Tech Solutions, LLC

from flask import (Flask, render_template, request, jsonify,
                   redirect, url_for, flash, session, g)
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urlparse
import json
import os
import threading
import time

import auth
import portfolio as pf
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)

_secret = os.environ.get("SP_SECRET_KEY")
if not _secret:
    raise RuntimeError(
        "SP_SECRET_KEY environment variable is not set. "
        "Generate one with: python3 -c \"import secrets; print(secrets.token_hex(32))\""
    )
app.secret_key = _secret
app.permanent_session_lifetime = timedelta(hours=12)

csrf = CSRFProtect(app)
limiter = Limiter(get_remote_address, app=app, default_limits=[])

DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(DIR, "config.json")
COMPANY_CACHE_FILE = os.path.join(DIR, "company_cache.json")
COMPANY_CACHE_TTL = 30 * 24 * 3600  # 30 days
_company_cache_lock = threading.Lock()


# ── Bootstrap ────────────────────────────────────────────────────────────────

auth.init_default_admin()


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def _is_safe_redirect(url):
    if not url:
        return False
    parsed = urlparse(url)
    return not parsed.netloc and not parsed.scheme and url.startswith('/')


@app.context_processor
def inject_globals():
    return {
        "current_year": datetime.utcnow().year,
        "session_user": session.get("username"),
        "session_role": session.get("role"),
    }


@app.before_request
def load_user():
    g.username = session.get("username")
    g.role = session.get("role")


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not g.username:
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not g.username:
            return redirect(url_for("login", next=request.path))
        if g.role != "admin":
            flash("Admin access required.", "danger")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated


@app.errorhandler(CSRFError)
def csrf_error(e):
    flash("Your session has expired or the request was invalid. Please try again.", "danger")
    return redirect(request.referrer or url_for("dashboard"))


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if g.username:
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if auth.verify_password(username, password):
            u = auth.get_user(username)
            session.permanent = True
            session["username"] = username
            session["role"] = u["role"]
            next_url = request.args.get("next", "")
            if not _is_safe_redirect(next_url):
                next_url = url_for("dashboard")
            return redirect(next_url)
        error = "Invalid username or password."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    notice = None
    if request.method == "POST":
        current = request.form.get("current", "")
        new_pw = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        if not auth.verify_password(g.username, current):
            notice = ("danger", "Current password is incorrect.")
        elif new_pw != confirm:
            notice = ("danger", "New passwords do not match.")
        elif len(new_pw) < 8:
            notice = ("danger", "Password must be at least 8 characters.")
        else:
            auth.set_password(g.username, new_pw)
            notice = ("success", "Password updated successfully.")
    return render_template("profile.html", notice=notice)


# ── Admin routes ──────────────────────────────────────────────────────────────

@app.route("/admin")
@admin_required
def admin_panel():
    users = auth.load_users()
    user_summaries = []
    for u in users:
        try:
            data = pf.load_portfolio(u["username"])
            holdings_count = len(data["holdings"])
            cash = data["cash"]
        except Exception:
            holdings_count = 0
            cash = 0.0
        user_summaries.append({**u, "holdings_count": holdings_count, "cash": cash})
    return render_template("admin.html", users=user_summaries)


@app.route("/admin/add-user", methods=["POST"])
@admin_required
def admin_add_user():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    email = request.form.get("email", "").strip()
    role = request.form.get("role", "user")
    starting_cash = request.form.get("starting_cash", "1000")

    if not username or not password:
        flash("Username and password are required.", "danger")
        return redirect(url_for("admin_panel"))

    ok, msg = auth.create_user(username, password, role=role, email=email)
    if ok:
        try:
            cash = float(starting_cash)
        except ValueError:
            cash = 1000.0
        pf.save_portfolio({"holdings": [], "cash": cash}, username)
        flash(msg, "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("admin_panel"))


@app.route("/admin/reset-password", methods=["POST"])
@admin_required
def admin_reset_password():
    username = request.form.get("username", "").strip()
    new_pw = request.form.get("new_password", "").strip()
    if not username or not new_pw:
        flash("Username and new password are required.", "danger")
        return redirect(url_for("admin_panel"))
    if auth.set_password(username, new_pw):
        flash(f'Password reset for "{username}".', "success")
    else:
        flash(f'User "{username}" not found.', "danger")
    return redirect(url_for("admin_panel"))


@app.route("/admin/delete-user", methods=["POST"])
@admin_required
def admin_delete_user():
    username = request.form.get("username", "").strip()
    if username == g.username:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for("admin_panel"))
    auth.delete_user(username)
    flash(f'User "{username}" deleted.', "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/set-role", methods=["POST"])
@admin_required
def admin_set_role():
    username = request.form.get("username", "").strip()
    role = request.form.get("role", "user")
    if username == g.username:
        flash("You cannot change your own role.", "danger")
        return redirect(url_for("admin_panel"))
    users = auth.load_users()
    for u in users:
        if u["username"] == username:
            u["role"] = role
            auth.save_users(users)
            flash(f'Role for "{username}" set to {role}.', "success")
            return redirect(url_for("admin_panel"))
    flash(f'User "{username}" not found.', "danger")
    return redirect(url_for("admin_panel"))


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def dashboard():
    summary = pf.portfolio_summary(g.username)
    config = load_config()
    return render_template("dashboard.html", summary=summary, config=config)


# ── Portfolio ─────────────────────────────────────────────────────────────────

@app.route("/portfolio")
@login_required
def portfolio_page():
    summary = pf.portfolio_summary(g.username)
    raw = pf.load_portfolio(g.username)
    return render_template("portfolio.html", summary=summary, cash=raw["cash"])


@app.route("/portfolio/add", methods=["POST"])
@login_required
def portfolio_add_route():
    ticker = request.form.get("ticker", "").strip()
    shares = request.form.get("shares", "").strip()
    price = request.form.get("price", "").strip()
    buy_date = request.form.get("buy_date", "").strip() or None

    if not ticker or not shares or not price:
        flash("All fields (ticker, shares, price) are required.", "danger")
        return redirect(url_for("portfolio_page"))
    try:
        ok, msg = pf.portfolio_add(ticker, float(shares), float(price), buy_date, g.username)
        flash(msg, "success" if ok else "danger")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    return redirect(url_for("portfolio_page"))


@app.route("/portfolio/sell", methods=["POST"])
@login_required
def portfolio_sell_route():
    ticker = request.form.get("ticker", "").strip()
    if not ticker:
        flash("Ticker is required.", "danger")
        return redirect(url_for("portfolio_page"))
    ok, msg = pf.portfolio_remove(ticker, g.username)
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("portfolio_page"))


@app.route("/portfolio/set-cash", methods=["POST"])
@login_required
def portfolio_set_cash_route():
    amount = request.form.get("amount", "").strip()
    if not amount:
        flash("Amount is required.", "danger")
        return redirect(url_for("portfolio_page"))
    try:
        ok, msg = pf.set_cash(float(amount), g.username)
        flash(msg, "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    return redirect(url_for("portfolio_page"))


# ── Screener (shared — market data is the same for all users) ─────────────────

screener_results = {"status": "idle", "data": None, "error": None}
screener_lock = threading.Lock()


@app.route("/screener")
@login_required
def screener_page():
    return render_template("screener.html", config=load_config())


@csrf.exempt
@app.route("/api/screener/run", methods=["POST"])
@login_required
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
@login_required
def screener_status():
    with screener_lock:
        return jsonify(screener_results)


# ── Sentiment ─────────────────────────────────────────────────────────────────

@app.route("/sentiment")
@login_required
def sentiment_page():
    return render_template("sentiment.html")


@csrf.exempt
@app.route("/api/sentiment", methods=["POST"])
@login_required
def sentiment_api():
    ticker = request.json.get("ticker", "").strip()
    if not ticker:
        return jsonify({"error": "Ticker required"}), 400
    from sentiment import analyze_sentiment
    return jsonify(analyze_sentiment(ticker))


# ── Recommendations (per-user — portfolio differs by user) ────────────────────

recommend_results = {}   # username -> {status, data, error}
recommend_lock = threading.Lock()


@app.route("/recommendations")
@login_required
def recommendations_page():
    return render_template("recommendations.html", config=load_config())


@csrf.exempt
@app.route("/api/recommendations/run", methods=["POST"])
@login_required
def recommendations_run():
    username = g.username
    with recommend_lock:
        if recommend_results.get(username, {}).get("status") == "running":
            return jsonify({"status": "already_running"})
        recommend_results[username] = {"status": "running", "data": None, "error": None}

    def _run(uname):
        try:
            from recommender import run_recommendations
            results = run_recommendations(uname)
            with recommend_lock:
                recommend_results[uname] = {"status": "done", "data": results, "error": None}
        except Exception as e:
            with recommend_lock:
                recommend_results[uname] = {"status": "error", "data": None, "error": str(e)}

    threading.Thread(target=_run, args=(username,), daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/api/recommendations/status")
@login_required
def recommendations_status():
    username = g.username
    with recommend_lock:
        return jsonify(recommend_results.get(username, {"status": "idle", "data": None, "error": None}))


# ── Company info (cached, for ticker hover popovers) ──

def _load_company_cache():
    if not os.path.exists(COMPANY_CACHE_FILE):
        return {}
    try:
        with open(COMPANY_CACHE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_company_cache(cache):
    try:
        with open(COMPANY_CACHE_FILE, "w") as f:
            json.dump(cache, f)
    except Exception:
        pass


def _truncate_summary(text, max_chars=400):
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_period = truncated.rfind(". ")
    if last_period > max_chars * 0.5:
        return truncated[:last_period + 1]
    return truncated.rstrip() + "…"


@app.route("/api/company/<ticker>")
@login_required
def company_info(ticker):
    ticker = ticker.upper().strip()
    if not ticker or not ticker.replace(".", "").replace("-", "").isalnum() or len(ticker) > 10:
        return jsonify({"error": "Invalid ticker"}), 400

    now = time.time()
    with _company_cache_lock:
        cache = _load_company_cache()
        entry = cache.get(ticker)
        if entry and (now - entry.get("ts", 0)) < COMPANY_CACHE_TTL:
            return jsonify(entry["data"])

    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info or {}
        data = {
            "ticker": ticker,
            "name": info.get("longName") or info.get("shortName") or ticker,
            "sector": info.get("sector") or "",
            "industry": info.get("industry") or "",
            "summary": _truncate_summary(info.get("longBusinessSummary", "")),
            "website": info.get("website") or "",
        }
    except Exception as e:
        return jsonify({"error": str(e), "ticker": ticker}), 502

    with _company_cache_lock:
        cache = _load_company_cache()
        cache[ticker] = {"ts": now, "data": data}
        _save_company_cache(cache)

    return jsonify(data)


# ── Settings (admin-only — global config affects all users) ───────────────────

@app.route("/settings")
@login_required
def settings_page():
    return render_template("settings.html", config=load_config())


@app.route("/settings/save", methods=["POST"])
@admin_required
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
