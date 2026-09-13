import json
import os
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import psycopg2
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, url_for

from services.market_data import MarketDataUnavailable, market_data
from services.symbols import MARKET_CONFIG, POPULAR_SYMBOLS, VALID_SYMBOLS

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


def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT")
    )


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
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT symbol FROM watchlist ORDER BY added_at DESC, id DESC")
            rows = cur.fetchall()
        return jsonify({"watchlist": [row[0] for row in rows]})
    finally:
        conn.close()


@app.route("/watchlist/quotes")
def watchlist_quotes():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT symbol FROM watchlist ORDER BY added_at DESC, id DESC")
            symbols = [row[0] for row in cur.fetchall()]
    finally:
        conn.close()

    quotes, _errors = market_data.get_quotes(symbols)
    return jsonify([quotes[symbol] for symbol in symbols if symbol in quotes])


@app.route("/watchlist/add", methods=["POST"])
def add_to_watchlist():
    data = request.get_json(silent=True) or {}
    symbol = str(data.get("symbol", "")).strip().upper()

    if not symbol:
        return jsonify({"error": "Missing symbol"}), 400
    if symbol not in VALID_SYMBOLS:
        return jsonify({"error": "Unsupported symbol"}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO watchlist (symbol) VALUES (%s) ON CONFLICT (symbol) DO NOTHING",
                (symbol,),
            )
        conn.commit()
        return jsonify({"status": "added", "symbol": symbol})
    except Exception as exc:
        conn.rollback()
        return jsonify({"error": str(exc)}), 500
    finally:
        conn.close()


@app.route("/watchlist/remove", methods=["DELETE"])
def remove_from_watchlist():
    data = request.get_json(silent=True) or {}
    symbol = str(data.get("symbol", "")).strip().upper()

    if not symbol:
        return jsonify({"error": "Missing symbol"}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM watchlist WHERE symbol = %s", (symbol,))
        conn.commit()
        return jsonify({"status": "removed", "symbol": symbol})
    except Exception as exc:
        conn.rollback()
        return jsonify({"error": str(exc)}), 500
    finally:
        conn.close()


if __name__ == "__main__":
    app.run(debug=True)
