const MARKET_CONFIG = JSON.parse(document.getElementById('market-config').textContent);
const VALID_SYMBOLS = MARKET_CONFIG.valid_symbols;
const MARKET_SYMBOLS = MARKET_CONFIG.market_symbols;
const MARKET_FLOW_SYMBOLS = MARKET_CONFIG.market_flow_symbols;
let watchlistQuotes = [];
let savedSymbols = new Set();
let searchRequestId = 0;
let searchTimer;
const searchQuoteCache = new Map();

function formatMetric(value, formatter) {
    const number = Number(value);
    return Number.isFinite(number) && number > 0 ? formatter(number) : '—';
}

function formatCompactCurrency(value) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        notation: 'compact',
        maximumFractionDigits: 1
    }).format(value);
}

function formatCompactNumber(value) {
    return new Intl.NumberFormat('en-US', {
        notation: 'compact',
        maximumFractionDigits: 1
    }).format(value);
}

function formatPrice(value) {
    return value.toFixed(2);
}

function showQuoteDetail(quote) {
    const detail = document.getElementById('ticker-detail');
    if (!detail) {
        return;
    }

    MarketDom.renderQuoteDetail(detail, quote, {
        formatMetric,
        formatPrice,
        formatCompactNumber,
        formatCompactCurrency
    });
}

function formatMarketSymbol(symbol) {
    const labels = {
        '^TNX': '10Y',
        '^VIX': 'VIX',
        'BTC-USD': 'BTC',
        'CL=F': 'Crude',
        'GC=F': 'Gold'
    };

    return labels[symbol] || symbol;
}

function renderMarketFlow(quotes, errors = {}) {
    const flowItems = document.getElementById('flow-items');
    if (!flowItems) {
        return;
    }

    flowItems.replaceChildren();
    for (const symbol of MARKET_FLOW_SYMBOLS) {
        const quote = quotes[symbol];
        const pill = document.createElement('span');
        pill.className = 'flow-pill';
        const label = document.createElement('strong');
        label.textContent = formatMarketSymbol(symbol);
        const movement = document.createElement('span');

        if (quote && Number.isFinite(quote.change)) {
            const sign = quote.change >= 0 ? '+' : '';
            movement.className = quote.change >= 0 ? 'positive' : 'negative';
            movement.textContent = `${sign}${quote.change.toFixed(2)}%`;
        } else {
            movement.textContent = 'Unavailable';
            movement.title = errors[symbol] || 'Change unavailable';
        }

        pill.append(label, movement);
        flowItems.appendChild(pill);
    }
}

function relativeTime(timestamp) {
    const publishedAt = new Date(timestamp).getTime();
    if (Number.isNaN(publishedAt)) {
        return 'Recently';
    }

    const minutes = Math.max(0, Math.floor((Date.now() - publishedAt) / 60000));
    if (minutes < 1) {
        return 'Just now';
    }
    if (minutes < 60) {
        return `${minutes}m ago`;
    }

    return `${Math.floor(minutes / 60)}h ago`;
}

function renderNews(articles) {
    const newsList = document.getElementById('news-list');
    if (!newsList) {
        return;
    }

    newsList.replaceChildren();
    for (const article of articles) {
        newsList.appendChild(MarketDom.createNewsArticle(article, relativeTime));
    }
}

async function loadNews() {
    const newsList = document.getElementById('news-list');
    const status = document.getElementById('news-status');
    if (!newsList) {
        return;
    }

    try {
        const response = await fetch('/news');
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Unable to load market news');
        }
        if (!Array.isArray(data.articles) || data.articles.length === 0) {
            MarketDom.renderNewsState(newsList, 'No market headlines are available right now.');
            return;
        }

        renderNews(data.articles);
        if (status) {
            status.textContent = 'Live';
        }
    } catch (error) {
        MarketDom.renderNewsState(newsList, error.message);
        if (status) {
            status.textContent = 'Offline';
        }
    }
}

function buildCard(quote, selected = false) {
    const card = document.createElement('div');
    card.className = `ticker-card${selected ? ' selected' : ''}`;
    card.id = `card-${quote.symbol}`;
    card.dataset.symbol = quote.symbol;

    const hasChange = Number.isFinite(quote.change);
    const changeColor = hasChange ? (quote.change >= 0 ? 'positive' : 'negative') : '';
    const changeSign = hasChange && quote.change >= 0 ? '+' : '';

    card.addEventListener('click', () => {
        document.querySelectorAll('.ticker-card').forEach((element) => {
            element.classList.remove('selected');
        });
        card.classList.add('selected');
        showQuoteDetail(quote);
    });

    const heading = document.createElement('h5');
    heading.textContent = `${quote.symbol} - ${quote.name}`;
    const price = document.createElement('h3');
    price.textContent = Number(quote.price).toFixed(2);
    const movement = document.createElement('p');
    movement.className = changeColor;
    movement.textContent = hasChange
        ? `${changeSign}${quote.change.toFixed(2)}%`
        : 'Change unavailable';
    card.append(heading, price, movement);

    if (document.body.dataset.page === 'watchlist') {
        const removeButton = document.createElement('button');
        removeButton.type = 'button';
        removeButton.className = 'remove-card-btn';
        removeButton.textContent = '×';
        removeButton.addEventListener('click', async (event) => {
            event.stopPropagation();
            const removed = await removeFromWatchlist(quote.symbol);
            if (!removed) {
                return;
            }
            await refreshWatchlistList();
            watchlistQuotes = watchlistQuotes.filter((item) => {
                return item.symbol !== quote.symbol;
            });
            renderWatchlistCards();
        });
        card.appendChild(removeButton);
    }
    return card;
}

function buildUnavailableCard(symbol, message = 'Market data unavailable') {
    const card = document.createElement('div');
    card.className = 'ticker-card ticker-card-unavailable';
    card.id = `card-${symbol}`;
    const heading = document.createElement('h5');
    heading.textContent = symbol;
    const status = document.createElement('p');
    status.textContent = message;
    card.append(heading, status);
    return card;
}

function updateWatchlistEmptyState() {
    const emptyState = document.getElementById('watchlist-empty');
    const count = document.getElementById('watchlist-count');
    if (emptyState) {
        emptyState.hidden = savedSymbols.size > 0;
    }
    if (count) {
        const suffix = savedSymbols.size === 1 ? '' : 's';
        count.textContent = `${savedSymbols.size} saved instrument${suffix}`;
    }
}

function renderWatchlistCards() {
    if (document.body.dataset.page !== 'watchlist') {
        return;
    }
    const grid = document.getElementById('cards-grid');
    const sortSelect = document.getElementById('watchlist-sort');
    if (!grid) {
        return;
    }

    const sortBy = sortSelect ? sortSelect.value : 'symbol';
    const sortedQuotes = [...watchlistQuotes].sort((first, second) => {
        if (sortBy === 'change') {
            return Number(second.change || 0) - Number(first.change || 0);
        }
        if (sortBy === 'market_cap') {
            return Number(second.market_cap || 0) - Number(first.market_cap || 0);
        }
        return first.symbol.localeCompare(second.symbol);
    });

    grid.replaceChildren();
    for (const quote of sortedQuotes) {
        grid.appendChild(buildCard(quote));
    }
    for (const symbol of savedSymbols) {
        if (!watchlistQuotes.some((quote) => quote.symbol === symbol)) {
            grid.appendChild(buildUnavailableCard(symbol));
        }
    }
    updateWatchlistEmptyState();
}

async function searchTicker() {
    clearTimeout(searchTimer);
    searchRequestId += 1;
    const ticker = document.getElementById('ticker-input').value.trim().toUpperCase();

    if (!ticker) {
        document.getElementById('search-dropdown').replaceChildren();
        return;
    }

    if (VALID_SYMBOLS.includes(ticker)) {
        await previewTicker(ticker);
        document.getElementById('ticker-input').value = '';
        document.getElementById('search-dropdown').replaceChildren();
        return;
    }

    document.getElementById('search-dropdown').replaceChildren();
}

async function selectTicker(symbol) {
    searchRequestId += 1;
    document.getElementById('ticker-input').value = '';
    document.getElementById('search-dropdown').replaceChildren();
    await previewTicker(symbol);
}

async function previewTicker(symbol) {
    try {
        const quote = await getSearchQuote(symbol);
        if (quote.symbol) {
            showQuoteDetail(quote);
        }
    } catch (error) {
        const detail = document.getElementById('ticker-detail');
        detail.textContent = `Quote unavailable for ${symbol}. Please try again later.`;
    }
}

async function getSearchQuote(symbol) {
    const cached = searchQuoteCache.get(symbol);
    if (cached && Date.now() - cached.createdAt < 60000) {
        return cached.promise;
    }

    const promise = fetch(`/quote?ticker=${encodeURIComponent(symbol)}`).then(async (response) => {
        if (!response.ok) {
            throw new Error('Quote unavailable');
        }
        return response.json();
    });

    searchQuoteCache.set(symbol, {
        createdAt: Date.now(),
        promise
    });

    promise.catch(() => {
        searchQuoteCache.delete(symbol);
    });

    return promise;
}

function createSparkline(values) {
    if (!Array.isArray(values) || values.length < 2) {
        const empty = document.createElement('span');
        empty.className = 'dropdown-chart-empty';
        empty.textContent = '—';
        return empty;
    }

    const width = 86;
    const height = 30;
    const minimum = Math.min(...values);
    const maximum = Math.max(...values);
    const spread = maximum - minimum || 1;
    const isRising = values[values.length - 1] >= values[0];
    const points = values.map((value, index) => {
        const x = 2 + (index / (values.length - 1)) * (width - 4);
        const y = height - 3 - ((value - minimum) / spread) * (height - 6);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
    });

    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', `dropdown-chart ${isRising ? 'positive' : 'negative'}`);
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    svg.setAttribute('aria-label', 'Five-day price trend');
    svg.setAttribute('role', 'img');

    const line = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
    line.setAttribute('points', points.join(' '));
    svg.appendChild(line);
    return svg;
}

function updateSearchStars() {
    document.querySelectorAll('.dropdown-star').forEach((button) => {
        const symbol = button.dataset.symbol;
        const isSaved = savedSymbols.has(symbol);
        button.classList.toggle('saved', isSaved);
        button.setAttribute('aria-label', `${isSaved ? 'Remove' : 'Add'} ${symbol} ${isSaved ? 'from' : 'to'} watchlist`);
        button.setAttribute('aria-pressed', String(isSaved));
        button.textContent = isSaved ? '★' : '☆';
    });
}

async function loadSavedSymbols() {
    try {
        const response = await fetch('/watchlist');
        if (!response.ok) {
            throw new Error('Watchlist unavailable');
        }
        const data = await response.json();
        savedSymbols = new Set(Array.isArray(data.watchlist) ? data.watchlist : []);
        updateSearchStars();
        return true;
    } catch (error) {
        console.error('Could not load saved symbols:', error);
        return false;
    }
}

async function toggleSearchStar(symbol, button) {
    button.disabled = true;
    const isSaved = savedSymbols.has(symbol);
    const endpoint = isSaved ? '/watchlist/remove' : '/watchlist/add';
    const method = isSaved ? 'DELETE' : 'POST';

    try {
        const response = await fetch(endpoint, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbol })
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Could not update watchlist');
        }

        if (isSaved) {
            savedSymbols.delete(symbol);
            watchlistQuotes = watchlistQuotes.filter((quote) => {
                return quote.symbol !== symbol;
            });
        } else {
            savedSymbols.add(symbol);
            if (document.body.dataset.page === 'watchlist') {
                try {
                    const quote = await getSearchQuote(symbol);
                    if (!watchlistQuotes.some((item) => item.symbol === symbol)) {
                        watchlistQuotes.push(quote);
                    }
                } catch (error) {
                    console.error('Saved symbol, but could not load its quote:', error);
                }
            }
        }

        updateSearchStars();
        renderWatchlistCards();
        await refreshWatchlistList();
    } catch (error) {
        alert(error.message || 'Could not update watchlist');
    } finally {
        button.disabled = false;
    }
}

function renderSearchResults(results, requestId) {
    const dropdown = document.getElementById('search-dropdown');
    dropdown.replaceChildren();

    if (results.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'dropdown-empty';
        empty.textContent = 'No supported symbols found';
        dropdown.appendChild(empty);
        return;
    }

    for (const result of results.slice(0, 5)) {
        const row = document.createElement('div');
        row.className = 'dropdown-item';

        const star = document.createElement('button');
        star.type = 'button';
        star.className = 'dropdown-star';
        star.dataset.symbol = result.symbol;
        star.addEventListener('click', () => {
            toggleSearchStar(result.symbol, star);
        });

        const select = document.createElement('button');
        select.type = 'button';
        select.className = 'dropdown-select';
        select.addEventListener('click', () => {
            selectTicker(result.symbol);
        });

        const identity = document.createElement('span');
        identity.className = 'dropdown-identity';
        const symbol = document.createElement('strong');
        symbol.textContent = result.symbol;
        const name = document.createElement('small');
        name.textContent = result.instrument_name;
        identity.append(symbol, name);

        const quoteLabel = document.createElement('span');
        quoteLabel.className = 'dropdown-quote';
        quoteLabel.textContent = 'Loading…';

        const chart = document.createElement('span');
        chart.className = 'dropdown-chart-wrap';
        chart.appendChild(createSparkline([]));

        select.append(identity, quoteLabel, chart);
        row.append(star, select);
        dropdown.appendChild(row);

        getSearchQuote(result.symbol).then((quote) => {
            if (requestId !== searchRequestId || !row.isConnected) {
                return;
            }

            if (Number(quote.price) > 0) {
                const hasChange = Number.isFinite(quote.change);
                quoteLabel.replaceChildren();
                const price = document.createElement('strong');
                price.textContent = Number(quote.price).toFixed(2);
                const movement = document.createElement('small');
                if (hasChange) {
                    movement.className = quote.change >= 0 ? 'positive' : 'negative';
                    movement.textContent = `${quote.change >= 0 ? '+' : ''}${quote.change.toFixed(2)}%`;
                } else {
                    movement.textContent = 'Change unavailable';
                }
                quoteLabel.append(price, movement);
                chart.replaceChildren(createSparkline(quote.sparkline));
            } else {
                quoteLabel.textContent = 'Data unavailable';
            }
        }).catch(() => {
            if (requestId === searchRequestId && row.isConnected) {
                quoteLabel.textContent = 'Data unavailable';
            }
        });
    }

    updateSearchStars();
}

async function runSymbolSearch() {
    const input = document.getElementById('ticker-input');
    const query = input.value.trim().toUpperCase();
    const requestId = ++searchRequestId;
    const dropdown = document.getElementById('search-dropdown');

    if (!query) {
        dropdown.replaceChildren();
        return;
    }

    try {
        const response = await fetch(`/search?q=${encodeURIComponent(query)}`);
        if (!response.ok) {
            throw new Error('Search unavailable');
        }
        const results = await response.json();
        if (requestId === searchRequestId) {
            renderSearchResults(results, requestId);
        }
    } catch (error) {
        if (requestId === searchRequestId) {
            dropdown.textContent = 'Search unavailable';
        }
    }
}

document.getElementById('ticker-input').addEventListener('keydown', async function (e) {
    if (e.key === 'Enter') {
        clearTimeout(searchTimer);
        searchRequestId += 1;
        const ticker = this.value.trim().toUpperCase();
        document.getElementById('search-dropdown').replaceChildren();

        if (VALID_SYMBOLS.includes(ticker)) {
            await previewTicker(ticker);
            this.value = '';
        }
    }
});

document.getElementById('ticker-input').addEventListener('input', function () {
    clearTimeout(searchTimer);
    searchRequestId += 1;
    if (!this.value.trim()) {
        document.getElementById('search-dropdown').replaceChildren();
        return;
    }
    searchTimer = setTimeout(runSymbolSearch, 250);
});

document.addEventListener('click', function (event) {
    const input = document.getElementById('ticker-input');
    const dropdown = document.getElementById('search-dropdown');
    if (!input.contains(event.target) && !dropdown.contains(event.target)) {
        clearTimeout(searchTimer);
        searchRequestId += 1;
        dropdown.replaceChildren();
    }
});

async function refreshWatchlistList() {
    const list = document.getElementById('watchlist-list');
    if (!list) {
        return;
    }

    try {
        const response = await fetch('/watchlist');
        const data = await response.json();
        const symbols = Array.isArray(data.watchlist) ? data.watchlist : [];

        list.replaceChildren();
        for (const symbol of symbols) {
            const pill = document.createElement('span');
            pill.className = 'watchlist-pill';
            const label = document.createElement('span');
            label.textContent = symbol;
            const button = document.createElement('button');
            button.type = 'button';
            button.setAttribute('aria-label', `Remove ${symbol}`);
            button.textContent = '×';
            button.addEventListener('click', async () => {
                const removed = await removeFromWatchlist(symbol);
                if (!removed) {
                    return;
                }
                await refreshWatchlistList();
                if (document.body.dataset.page === 'watchlist') {
                    watchlistQuotes = watchlistQuotes.filter((item) => {
                        return item.symbol !== symbol;
                    });
                    renderWatchlistCards();
                } else {
                    const card = document.getElementById(`card-${symbol}`);
                    if (card) {
                        card.remove();
                    }
                }
            });
            pill.append(label, button);
            list.appendChild(pill);
        }
    } catch (error) {
        console.error('Could not refresh watchlist:', error);
    }
}

async function removeFromWatchlist(symbol) {
    if (!symbol) {
        return;
    }

    const response = await fetch('/watchlist/remove', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol })
    });

    if (!response.ok) {
        const data = await response.json();
        alert(data.error || 'Unable to remove symbol');
        return false;
    }
    savedSymbols.delete(symbol);
    updateSearchStars();
    return true;
}

async function loadDashboardQuotes(savedSymbolsPromise) {
    const page = document.body.dataset.page;
    let cardSymbols;
    let watchlistAvailable = true;
    if (page === 'watchlist') {
        watchlistAvailable = await savedSymbolsPromise;
        cardSymbols = watchlistAvailable ? [...savedSymbols] : [];
    } else if (page === 'markets') {
        cardSymbols = MARKET_SYMBOLS;
    } else {
        cardSymbols = MARKET_CONFIG.other_default_symbols;
    }

    const symbols = [...new Set([...cardSymbols, ...MARKET_FLOW_SYMBOLS])];
    const grid = document.getElementById('cards-grid');
    let quotes = {};
    let errors = {};

    try {
        const response = await fetch(`/api/quotes?symbols=${encodeURIComponent(symbols.join(','))}`);
        if (!response.ok) {
            throw new Error('Market data unavailable');
        }
        const data = await response.json();
        quotes = data.quotes || {};
        errors = data.errors || {};
    } catch (error) {
        for (const symbol of symbols) {
            errors[symbol] = 'Market data unavailable';
        }
    }

    renderMarketFlow(quotes, errors);
    for (const [symbol, quote] of Object.entries(quotes)) {
        searchQuoteCache.set(symbol, {
            createdAt: Date.now(),
            promise: Promise.resolve(quote)
        });
    }

    if (page === 'watchlist') {
        if (!watchlistAvailable) {
            grid.replaceChildren(buildUnavailableCard('Watchlist', 'Watchlist unavailable. Please try again later.'));
            const emptyState = document.getElementById('watchlist-empty');
            emptyState.hidden = true;
            return;
        }

        watchlistQuotes = cardSymbols.filter((symbol) => {
            return Boolean(quotes[symbol]);
        }).map((symbol) => {
            return quotes[symbol];
        });
        renderWatchlistCards();
        return;
    }

    grid.replaceChildren();
    for (const symbol of cardSymbols) {
        grid.appendChild(quotes[symbol]
            ? buildCard(quotes[symbol])
            : buildUnavailableCard(symbol, errors[symbol]));
    }

    const firstAvailable = cardSymbols.find((symbol) => {
        return Boolean(quotes[symbol]);
    });
    if (firstAvailable) {
        showQuoteDetail(quotes[firstAvailable]);
    } else {
        document.getElementById('ticker-detail').textContent = 'Market data unavailable. Please try again later.';
    }
}

document.addEventListener('DOMContentLoaded', function () {
    const savedSymbolsPromise = loadSavedSymbols();
    const watchlistSort = document.getElementById('watchlist-sort');
    if (watchlistSort) {
        watchlistSort.addEventListener('change', () => {
            renderWatchlistCards();
        });
    }
    refreshWatchlistList();
    loadDashboardQuotes(savedSymbolsPromise);
    loadNews();
    window.setInterval(loadNews, 60000);
});
