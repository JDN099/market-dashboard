import os
import psycopg2
import yfinance as yf
from flask import Flask, render_template, jsonify, request
from dotenv import load_dotenv

app = Flask(__name__)
load_dotenv()

def get_db_connection():
    conn = psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT")
    )
    return conn

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/quote')
def quote():
    ticker = request.args.get('ticker', '').upper()
    stock = yf.Ticker(ticker)
    info = stock.info
    data = {
        'symbol': ticker,
        'name': info.get('longName'),
        'price': info.get('currentPrice') or info.get('regularMarketPrice'),
        'change': info.get('regularMarketChangePercent'),
    }
    return jsonify(data)

# Watchlist Routes
@app.route('/watchlist')
def watchlist():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT symbol FROM watchlist"
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify({'watchlist': [row[0] for row in rows]})

@app.route('/watchlist/add', methods=['POST'])
def add_to_watchlist():
    symbol = request.json.get('symbol')
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO watchlist (symbol) VALUES (%s)"
    , (symbol,)
    )
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'status': 'added', 'symbol': symbol})

@app.route('/watchlist/remove', methods=['DELETE'])
def remove_from_watchlist():
    symbol = request.json.get('symbol')
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM watchlist WHERE symbol = %s"
        , (symbol,)
    )
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'status': 'removed', 'symbol': symbol})


if __name__ == '__main__':
    app.run(debug=True)