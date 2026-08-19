import yfinance as yf
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)

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

if __name__ == '__main__':
    app.run(debug=True)