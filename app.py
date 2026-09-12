import math
import os

import psycopg2
import yfinance as yf
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
load_dotenv()

popular_symbols = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "INTC",
    "SPY", "QQQ", "IWM", "DIA", "V", "JPM", "XOM", "BRK-B", "NFLX",
    "NQ=F", "ES=F", "CL=F", "GC=F", "BTC-USD", "ETH-USD"
]
VALID_SYMBOLS = set(symbol.upper() for symbol in popular_symbols)
PAGE_TITLES = {
    "overview": "Overview",
    "markets": "Markets",
    "watchlist": "Watchlist",
    "economic-calendar": "Economic Calendar",
    "earnings": "Earnings",
    "sentiment": "Sentiment",
}


def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT")
    )


def safe_float(value, default=0.0):
    try:
        number = float(value)
        if not math.isfinite(number):
            return default
        return number
    except (TypeError, ValueError):
        return default


def get_quote_for_symbol(symbol):
    ticker = str(symbol or "").strip().upper()
    if not ticker:
        return {"symbol": "", "name": "", "price": 0.0, "change": 0.0}

    try:
        stock = yf.Ticker(ticker)
        info = stock.info or {}
        hist = stock.history(period="5d", auto_adjust=False)

        name = info.get("shortName") or info.get("longName") or ticker
        is_futures = ticker.endswith("=F")

        price = safe_float(info.get("regularMarketPrice"))
        previous_reference = safe_float(
            info.get("regularMarketPreviousClose") if is_futures else info.get("previousClose")
        )

        if hist is not None and not hist.empty:
            latest = hist.iloc[-1]
            previous = hist.iloc[-2] if len(hist) > 1 else latest
            price = safe_float(latest.get("Close"), price)

            if not is_futures and previous_reference == 0.0:
                previous_reference = safe_float(previous.get("Close"), previous_reference)

        if price == 0.0 and safe_float(info.get("regularMarketPrice")) != 0.0:
            price = safe_float(info.get("regularMarketPrice"))
        if previous_reference == 0.0 and is_futures and safe_float(info.get("regularMarketPreviousClose")) != 0.0:
            previous_reference = safe_float(info.get("regularMarketPreviousClose"))
        if previous_reference == 0.0 and safe_float(info.get("previousClose")) != 0.0:
            previous_reference = safe_float(info.get("previousClose"))
        if previous_reference == 0.0:
            previous_reference = price

        change = 0.0 if previous_reference == 0 else ((price - previous_reference) / previous_reference) * 100

        market_cap = safe_float(info.get("marketCap"), 0.0)
        volume = safe_float(info.get("regularMarketVolume"), 0.0)
        day_high = safe_float(info.get("regularMarketDayHigh"), price)
        day_low = safe_float(info.get("regularMarketDayLow"), price)

        return {
            "symbol": ticker,
            "name": name,
            "price": round(safe_float(price), 2),
            "change": round(safe_float(change), 2),
            "market_cap": market_cap,
            "volume": volume,
            "day_high": day_high,
            "day_low": day_low,
        }
    except Exception:
        return {
            "symbol": ticker,
            "name": ticker,
            "price": 0.0,
            "change": 0.0,
            "market_cap": 0.0,
            "volume": 0.0,
            "day_high": 0.0,
            "day_low": 0.0,
        }


def render_dashboard(page="overview"):
    return render_template("index.html", page=page, title=PAGE_TITLES.get(page, "Overview"))


@app.route("/")
def index():
    return render_dashboard("overview")


@app.route("/overview")
def overview():
    return render_dashboard("overview")


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


@app.route("/quote")
def quote():
    ticker = request.args.get("ticker", "").strip().upper()
    if ticker not in VALID_SYMBOLS:
        return jsonify({"error": "Unsupported symbol"}), 400
    return jsonify(get_quote_for_symbol(ticker))


@app.route("/search")
def search():
    query = request.args.get("q", "").strip().upper()
    if not query:
        return jsonify([])

    matches = []
    seen = set()
    for symbol in popular_symbols:
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

    quotes = [get_quote_for_symbol(symbol) for symbol in symbols]
    return jsonify(quotes)


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