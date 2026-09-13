"""The symbol catalog shared by Flask pages and browser scripts."""

POPULAR_SYMBOLS = (
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "INTC",
    "SPY", "QQQ", "IWM", "DIA", "V", "JPM", "XOM", "BRK-B", "NFLX",
    "NQ=F", "ES=F", "CL=F", "GC=F", "BTC-USD", "ETH-USD", "^VIX", "^TNX",
)

VALID_SYMBOLS = frozenset(POPULAR_SYMBOLS)

MARKET_SYMBOLS = (
    "SPY", "QQQ", "IWM", "DIA", "NQ=F", "ES=F", "CL=F", "GC=F",
)

MARKET_FLOW_SYMBOLS = (
    "SPY", "QQQ", "IWM", "DIA", "^VIX", "^TNX", "CL=F", "GC=F", "BTC-USD",
)

OTHER_DEFAULT_SYMBOLS = (
    "SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA",
)

MARKET_CONFIG = {
    "valid_symbols": POPULAR_SYMBOLS,
    "market_symbols": MARKET_SYMBOLS,
    "market_flow_symbols": MARKET_FLOW_SYMBOLS,
    "other_default_symbols": OTHER_DEFAULT_SYMBOLS,
}
