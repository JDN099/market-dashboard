import os
import psycopg2
import requests
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

# Quote Routes
@app.route('/quote')
def quote():
    ticker = request.args.get('ticker', '').upper()
    api_key = os.getenv("TWELVEDATA_API_KEY")
    response = requests.get(f'https://api.twelvedata.com/quote?symbol={ticker}&apikey={api_key}')
    info = response.json()
    data = {
        'symbol': ticker,
        'name': info.get('name'),
        'price': float(info.get('close', 0)),
        'change': float(info.get('percent_change', 0)),
    }
    return jsonify(data)

# Search Routes
@app.route('/search')
def search():
    query = request.args.get('q', '').upper()
    api_key = os.getenv("TWELVEDATA_API_KEY")
    response = requests.get(f'https://api.twelvedata.com/symbol_search?symbol={query}&apikey={api_key}')
    info = response.json()
    data = info.get('data', [])
    us_only = [r for r in data if r.get('country') == 'United States']
    seen = set()
    unique = []
    for r in us_only:
        if r['symbol'] not in seen:
            seen.add(r['symbol'])
            unique.append(r)
    return jsonify(unique)


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