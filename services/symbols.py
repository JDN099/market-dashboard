"""The symbol catalog shared by Flask pages and browser scripts."""

POPULAR_SYMBOLS = (
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "INTC",
    "SPY", "QQQ", "IWM", "DIA", "V", "JPM", "XOM", "BRK-B", "NFLX",
    "GLD", "USO", "BTC/USD", "EUR/USD",
)

VALID_SYMBOLS = frozenset(POPULAR_SYMBOLS)

MARKET_SYMBOLS = (
    "SPY", "QQQ", "IWM", "DIA", "GLD", "USO",
)

MARKET_FLOW_SYMBOLS = (
    "SPY", "QQQ", "IWM", "DIA", "GLD", "USO", "BTC/USD", "EUR/USD",
)

OTHER_DEFAULT_SYMBOLS = (
    "SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA",
)

SYMBOL_NAMES = {
    "SPY": "SPDR S&P 500 ETF Trust",
    "QQQ": "Invesco QQQ Trust ETF",
    "IWM": "iShares Russell 2000 ETF",
    "DIA": "SPDR Dow Jones Industrial Average ETF",
    "GLD": "SPDR Gold Shares ETF",
    "USO": "United States Oil Fund ETF",
    "BTC/USD": "Bitcoin / U.S. Dollar",
    "EUR/USD": "Euro / U.S. Dollar",
}

SYMBOL_EXCHANGES = {
    "BTC/USD": "Cryptocurrency",
    "EUR/USD": "Forex",
}

MARKET_CONFIG = {
    "valid_symbols": POPULAR_SYMBOLS,
    "market_symbols": MARKET_SYMBOLS,
    "market_flow_symbols": MARKET_FLOW_SYMBOLS,
    "other_default_symbols": OTHER_DEFAULT_SYMBOLS,
}
