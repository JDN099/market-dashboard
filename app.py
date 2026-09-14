import json
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from flask import Flask, g, jsonify, redirect, render_template, request, url_for

from services.market_data import MarketDataUnavailable, market_data
from services.symbols import MARKET_CONFIG, POPULAR_SYMBOLS, VALID_SYMBOLS
from services.watchlist import WatchlistStore

app = Flask(__name__)
load_dotenv()

PAGE_TITLES = {
    "markets": "Markets",
    "watchlist": "Watchlist",
    "economic-calendar": "Economic Calendar",
    "earnings": "Earnings",
    "sentiment": "Sentiment",
}
NEWS_CACHE_TTL_SECONDS = 600
news_cache = {}
watchlist_store = WatchlistStore()
VISITOR_COOKIE_NAME = "marketv_visitor"
VISITOR_COOKIE_MAX_AGE = 365 * 24 * 60 * 60
VISITOR_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}\Z")
CRITICAL_NEWS_KEYWORDS = (
    "attack",
    "bankruptcy",
    "emergency",
    "halt",
    "iran",
    "sanctions",
    "trump",
    "war",
)
WATCH_NEWS_KEYWORDS = (
    "acquisition",
    "cpi",
    "earnings",
    "fed",
    "jobs report",
    "merger",
    "tariff",
)
DEFAULT_NEWS_DOMAINS = (
    "apnews.com",
    "cnbc.com",
    "finance.yahoo.com",
    "marketwatch.com",
    "reuters.com",
)


def current_visitor_id():
    if hasattr(g, "visitor_id"):
        return g.visitor_id

    cookie_value = request.cookies.get(VISITOR_COOKIE_NAME, "")
    if VISITOR_ID_PATTERN.fullmatch(cookie_value):
        g.visitor_id = cookie_value
    else:
        g.visitor_id = secrets.token_urlsafe(32)
        g.new_visitor_id = True
    return g.visitor_id


@app.after_request
def attach_visitor_cookie(response):
    if getattr(g, "new_visitor_id", False):
        secure = request.is_secure or os.getenv("VISITOR_COOKIE_SECURE", "").lower() in (
            "1", "true", "yes"
        )
        response.set_cookie(
            VISITOR_COOKIE_NAME,
            g.visitor_id,
            max_age=VISITOR_COOKIE_MAX_AGE,
            httponly=True,
            secure=secure,
            samesite="Lax",
        )
    return response


def classify_news_importance(title):
    headline = str(title or "").lower()
    if any(keyword in headline for keyword in CRITICAL_NEWS_KEYWORDS):
        return "critical"
    if any(keyword in headline for keyword in WATCH_NEWS_KEYWORDS):
        return "watch"
    return "normal"


def get_preferred_news_domains():
    configured_domains = os.getenv("MARKETAUX_DOMAINS", "")
    if configured_domains.strip():
        return configured_domains

    return ",".join(DEFAULT_NEWS_DOMAINS)


def get_market_news(hours=None, page=1):
    now = time.time()
    cache_key = (hours, page)
    cached_result = news_cache.get(cache_key)
    if cached_result and now - cached_result["updated_at"] < NEWS_CACHE_TTL_SECONDS:
        return cached_result["articles"]

    api_key = os.getenv("MARKETAUX_API_KEY")
    if not api_key:
        raise RuntimeError("Marketaux API key is not configured")

    query_params = {
        "api_token": api_key,
        "domains": get_preferred_news_domains(),
        "language": "en",
        "limit": 3,
        "page": page,
    }
    if hours:
        earliest_article = datetime.now(timezone.utc) - timedelta(hours=hours)
        query_params["published_after"] = earliest_article.strftime("%Y-%m-%dT%H:%M:%S")

    query = urlencode(query_params)
    request = Request(
        f"https://api.marketaux.com/v1/news/all?{query}",
        headers={
            "Accept": "application/json",
            "User-Agent": "MarketV/1.0",
        },
    )

    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError("Unable to load market news") from exc

    articles = []
    for article in payload.get("data", []):
        title = article.get("title") or "Untitled market update"
        symbols = [
            entity.get("symbol")
            for entity in article.get("entities", [])
            if entity.get("symbol")
        ]
        articles.append(
            {
                "title": title,
                "url": article.get("url") or "",
                "source": article.get("source") or "Market news",
                "published_at": article.get("published_at") or "",
                "symbols": symbols[:3],
                "importance": classify_news_importance(title),
            }
        )

    news_cache[cache_key] = {
        "articles": articles,
        "updated_at": now,
    }
    return articles


def render_dashboard(page="overview"):
    return render_template(
        "index.html",
        page=page,
        title=PAGE_TITLES.get(page, "Overview"),
        market_config=MARKET_CONFIG,
    )


@app.route("/")
def index():
    return redirect(url_for("markets"))


@app.route("/overview")
def overview():
    return redirect(url_for("markets"))


@app.route("/markets")
def markets():
    return render_dashboard("markets")


@app.route("/watchlist-page")
def watchlist_page():
    return render_dashboard("watchlist")


@app.route("/economic-calendar")
def economic_calendar():
    return render_dashboard("economic-calendar")


@app.route("/earnings")
def earnings():
    return render_dashboard("earnings")


@app.route("/sentiment")
def sentiment():
    return render_dashboard("sentiment")


@app.route("/news-page")
def news_page():
    return render_template(
        "news.html",
        page="news",
        title="News",
        market_config=MARKET_CONFIG,
    )


@app.route("/quote")
def quote():
    ticker = request.args.get("ticker", "").strip().upper()
    if ticker not in VALID_SYMBOLS:
        return jsonify({"error": "Unsupported symbol"}), 400
    try:
        return jsonify(market_data.get_quote(ticker))
    except MarketDataUnavailable as exc:
        return jsonify({"error": str(exc)}), 503


@app.route("/api/quotes")
def batch_quotes():
    raw_symbols = request.args.get("symbols", "")
    symbols = list(dict.fromkeys(
        symbol.strip().upper() for symbol in raw_symbols.split(",") if symbol.strip()
    ))
    if not symbols or len(symbols) > 30:
        return jsonify({"error": "Provide 1 to 30 symbols"}), 400
    if any(symbol not in VALID_SYMBOLS for symbol in symbols):
        return jsonify({"error": "Unsupported symbol"}), 400

    quotes, errors = market_data.get_quotes(symbols)
    status = 200 if quotes else 503
    return jsonify({"quotes": quotes, "errors": errors}), status


@app.route("/api/history")
def history():
    ticker = request.args.get("symbol", "").strip().upper()
    if ticker not in VALID_SYMBOLS:
        return jsonify({"error": "Unsupported symbol"}), 400

    period = request.args.get("period", "1mo")
    interval = request.args.get("interval", "1d")
    try:
        points = market_data.get_history(ticker, period=period, interval=interval)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except MarketDataUnavailable as exc:
        return jsonify({"error": str(exc)}), 503

    return jsonify({
        "symbol": ticker,
        "period": period,
        "interval": interval,
        "points": points,
    })


@app.route("/search")
def search():
    query = request.args.get("q", "").strip().upper()
    if not query:
        return jsonify([])

    matches = []
    seen = set()
    for symbol in POPULAR_SYMBOLS:
        if query in symbol:
            label = symbol.replace("=F", " futures")
            if symbol not in seen:
                seen.add(symbol)
                matches.append({
                    "symbol": symbol,
                    "instrument_name": label,
                    "exchange": "Yahoo Finance"
                })
    return jsonify(matches[:10])


@app.route("/news")
def news():
    range_options = {
        "24h": 24,
        "7d": 24 * 7,
    }
    time_range = request.args.get("range", "")
    hours = range_options.get(time_range)
    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        page = 1

    try:
        return jsonify(
            {
                "articles": get_market_news(hours=hours, page=page),
                "page": page,
            }
        )
    except RuntimeError as exc:
        return jsonify(
            {
                "error": str(exc),
            }
        ), 503


@app.route("/watchlist")
def watchlist():
    try:
        symbols = watchlist_store.get_symbols(current_visitor_id())
        return jsonify({"watchlist": symbols})
    except Exception:
        return jsonify({"error": "Watchlist unavailable"}), 503


@app.route("/watchlist/add", methods=["POST"])
def add_to_watchlist():
    data = request.get_json(silent=True) or {}
    symbol = str(data.get("symbol", "")).strip().upper()

    if not symbol:
        return jsonify({"error": "Missing symbol"}), 400
    if symbol not in VALID_SYMBOLS:
        return jsonify({"error": "Unsupported symbol"}), 400

    try:
        watchlist_store.add_symbol(current_visitor_id(), symbol)
        return jsonify({"status": "added", "symbol": symbol})
    except Exception:
        return jsonify({"error": "Watchlist unavailable"}), 503


@app.route("/watchlist/remove", methods=["DELETE"])
def remove_from_watchlist():
    data = request.get_json(silent=True) or {}
    symbol = str(data.get("symbol", "")).strip().upper()

    if not symbol:
        return jsonify({"error": "Missing symbol"}), 400

    try:
        watchlist_store.remove_symbol(current_visitor_id(), symbol)
        return jsonify({"status": "removed", "symbol": symbol})
    except Exception:
        return jsonify({"error": "Watchlist unavailable"}), 503


if __name__ == "__main__":
    app.run(debug=True)
