const MARKET_CONFIG = JSON.parse(document.getElementById('market-config').textContent);
const VALID_SYMBOLS = MARKET_CONFIG.valid_symbols;
const MARKET_SYMBOLS = MARKET_CONFIG.market_symbols;
const MARKET_FLOW_SYMBOLS = MARKET_CONFIG.market_flow_symbols;
let watchlistQuotes = [];
let savedSymbols = new Set();
let savedSymbolsReady = Promise.resolve(false);
let selectedHistoryRequestId = 0;
let selectedHistoryPeriod = '1mo';
let selectedQuoteSymbol = null;
const HISTORY_PERIODS = [
    { value: '1d', label: '1D', interval: '5m' },
    { value: '5d', label: '5D', interval: '1h' },
    { value: '1mo', label: '1M', interval: '1d' },
    { value: '3mo', label: '3M', interval: '1d' },
    { value: '1y', label: '1Y', interval: '1d' }
];
const PROVIDER_BATCH_SIZE = 8;

async function fetchQuoteBatches(symbols) {
    const result = {
        quotes: {},
        errors: {}
    };

    for (let start = 0; start < symbols.length; start += PROVIDER_BATCH_SIZE) {
        const batch = symbols.slice(start, start + PROVIDER_BATCH_SIZE);
        const response = await fetch(`/api/quotes?symbols=${encodeURIComponent(batch.join(','))}`);
        const data = await response.json();
        Object.assign(result.quotes, data.quotes || {});
        Object.assign(result.errors, data.errors || {});
        if (!response.ok && !data.errors) {
            for (const symbol of batch) {
                result.errors[symbol] = data.error || 'Market data unavailable';
            }
        }
    }

    return result;
}

const searchQuotes = QuoteClient.create(async (symbols) => {
    return fetchQuoteBatches(symbols);
});
const historyClient = HistoryClient.create(
    async (symbol, period, interval) => {
        const response = await fetch(`/api/history?symbol=${encodeURIComponent(symbol)}&period=${period}&interval=${interval}`);
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Price history unavailable');
        }
        const points = data.points;
        points.dataState = data.data_state || 'delayed';
        return points;
    },
    async (symbols) => {
        const response = await fetch(`/api/history/batch?symbols=${encodeURIComponent(symbols.join(','))}`);
        const data = await response.json();
        if (!response.ok && !data.errors) {
            throw new Error(data.error || 'Price history unavailable');
        }
        for (const [symbol, points] of Object.entries(data.histories || {})) {
            points.dataState = data.states?.[symbol] || 'delayed';
        }
        return data;
    }
);
const searchController = SearchController.create({
    validSymbols: VALID_SYMBOLS,
    quoteClient: searchQuotes,
    historyClient,
    loadIntradaySparkline,
    onPreview: previewTicker,
    onToggleStar: toggleSearchStar,
    onResultsRendered: updateSearchStars
});

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
    return value < 10 ? value.toFixed(4) : value.toFixed(2);
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
    selectedQuoteSymbol = quote.symbol;
    document.querySelectorAll('.ticker-card').forEach((card) => {
        card.classList.toggle('selected', card.dataset.symbol === selectedQuoteSymbol);
    });
    renderSelectedHistory(detail, quote);
}

function requestHistory(symbol, period) {
    const option = HISTORY_PERIODS.find((item) => item.value === period);
    return historyClient.getOne(symbol, option.value, option.interval);
}

function loadIntradaySparkline(symbol, container, historyRequest, quoteRequest) {
    container.title = `${symbol} 1D intraday prices; color follows daily percentage change`;
    const changeRequest = quoteRequest.then((quote) => quote.change, () => null);
    return Promise.all([historyRequest, changeRequest]).then(([points, dailyChange]) => {
        if (container.isConnected) {
            const closes = points.map((point) => point.close);
            const graphic = container.querySelector('.sparkline-graphic');
            graphic.replaceChildren(MarketCharts.createSparkline(closes, { dailyChange }));
            if (points.dataState === 'stale') {
                container.title = `${symbol} stale cached 1D prices`;
            }
        }
        return { available: true };
    }).catch((error) => {
        if (container.isConnected) {
            container.title = error.message || `${symbol} 1D trend unavailable`;
            const graphic = container.querySelector('.sparkline-graphic');
            graphic.replaceChildren(MarketCharts.createSparkline([]));
        }
        return {
            available: false,
            rateLimited: String(error.message || '').toLowerCase().includes('rate limit')
        };
    });
}

function loadCardSparklines(quotes, allowRateLimitRetry = true) {
    if (quotes.length === 0) {
        return;
    }
    const symbols = quotes.map((quote) => quote.symbol);
    const requests = historyClient.getIntradayMany(symbols);
    const renderRequests = [];
    for (const quote of quotes) {
        const card = document.getElementById(`card-${quote.symbol}`);
        const container = card && card.querySelector('.card-sparkline');
        if (container) {
            renderRequests.push(loadIntradaySparkline(
                quote.symbol,
                container,
                requests.get(quote.symbol),
                Promise.resolve(quote)
            ));
        }
    }

    Promise.all(renderRequests).then((results) => {
        const wasRateLimited = results.some((result) => result.rateLimited);
        if (allowRateLimitRetry && wasRateLimited) {
            window.setTimeout(() => {
                loadCardSparklines(quotes, false);
            }, 61000);
        }
    });
}

function renderSelectedHistory(detail, quote) {
    const requestId = ++selectedHistoryRequestId;
    const section = document.createElement('section');
    section.className = 'detail-history';
    const header = document.createElement('div');
    header.className = 'history-heading';
    const title = document.createElement('h3');
    title.textContent = 'Price history';
    const summary = document.createElement('div');
    summary.className = 'history-summary';
    summary.appendChild(title);
    const controls = document.createElement('div');
    controls.className = 'history-periods';
    controls.setAttribute('role', 'group');
    controls.setAttribute('aria-label', 'Chart time range');

    for (const option of HISTORY_PERIODS) {
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = option.label;
        button.className = option.value === selectedHistoryPeriod ? 'active' : '';
        button.setAttribute('aria-pressed', String(option.value === selectedHistoryPeriod));
        button.addEventListener('click', () => {
            if (selectedHistoryPeriod === option.value) {
                return;
            }
            selectedHistoryPeriod = option.value;
            renderSelectedHistory(detail, quote);
        });
        controls.appendChild(button);
    }

    header.append(summary, controls);
    const content = document.createElement('div');
    content.className = 'history-content';
    content.textContent = 'Loading price history…';
    section.append(header, content);
    const previous = detail.querySelector('.detail-history');
    if (previous) {
        previous.replaceWith(section);
    } else {
        detail.appendChild(section);
    }

    const period = selectedHistoryPeriod;
    requestHistory(quote.symbol, period).then((points) => {
        if (requestId !== selectedHistoryRequestId || !section.isConnected) {
            return;
        }
        const label = HISTORY_PERIODS.find((item) => item.value === period).label;
        const periodChange = MarketCharts.calculatePeriodChange(points);
        const chart = MarketCharts.createHistoryChart(points, quote.symbol, label, {
            changeOverride: null
        });
        if (periodChange === null || !chart) {
            content.textContent = 'Price history unavailable for this range.';
            return;
        }
        const change = document.createElement('span');
        change.className = 'history-change';
        if (periodChange > 0) {
            change.classList.add('positive');
        } else if (periodChange < 0) {
            change.classList.add('negative');
        }
        change.textContent = `${label} ${MarketCharts.formatPeriodChange(periodChange)}`;
        change.title = 'Change from first to last plotted price';
        summary.appendChild(change);
        if (points.dataState === 'stale') {
            const state = document.createElement('span');
            state.className = 'data-state-label data-state-label--stale';
            state.textContent = 'Stale cached history';
            summary.appendChild(state);
        }
        const dates = document.createElement('div');
        dates.className = 'history-dates';
        const start = document.createElement('span');
        start.textContent = MarketCharts.formatHistoryDate(points[0].time, period);
        const end = document.createElement('span');
        end.textContent = MarketCharts.formatHistoryDate(points[points.length - 1].time, period);
        dates.append(start, end);
        content.replaceChildren(chart, dates);
    }).catch((error) => {
        if (requestId === selectedHistoryRequestId && section.isConnected) {
            content.textContent = error.message || 'Price history unavailable right now.';
        }
    });
}

function buildCard(quote, selected = false) {
    const card = document.createElement('div');
    card.className = `ticker-card${selected ? ' selected' : ''}`;
    card.id = `card-${quote.symbol}`;
    card.dataset.symbol = quote.symbol;

    const changeDisplay = MarketUi.describeChange(quote.change);

    card.addEventListener('click', () => {
        showQuoteDetail(quote);
    });

    const heading = document.createElement('h5');
    heading.textContent = `${quote.symbol} - ${quote.name}`;
    const price = document.createElement('h3');
    price.textContent = formatPrice(Number(quote.price));
    const movement = document.createElement('p');
    movement.className = changeDisplay.className;
    movement.title = quote.change_basis || 'Daily change';
    movement.textContent = changeDisplay.text;
    const sparkline = MarketUi.createSparklineShell('card-sparkline');
    const footer = document.createElement('div');
    footer.className = 'card-footer';
    footer.append(movement, sparkline);
    card.append(heading, price, footer);

    if (quote.stale) {
        const state = document.createElement('span');
        state.className = 'data-state-label data-state-label--stale';
        state.textContent = 'Stale cached data';
        card.appendChild(state);
    }

    if (document.body.dataset.page === 'watchlist') {
        const removeButton = document.createElement('button');
        removeButton.type = 'button';
        removeButton.className = 'remove-card-btn';
        removeButton.textContent = '×';
        removeButton.addEventListener('click', async (event) => {
            event.stopPropagation();
            await removeSavedSymbol(quote.symbol);
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
    WatchlistUi.renderSummary(emptyState, count, savedSymbols.size);
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
        if (sortBy === 'price') {
            return Number(second.price || 0) - Number(first.price || 0);
        }
        return first.symbol.localeCompare(second.symbol);
    });

    grid.replaceChildren();
    for (const quote of sortedQuotes) {
        grid.appendChild(buildCard(quote, quote.symbol === selectedQuoteSymbol));
    }
    for (const symbol of savedSymbols) {
        if (!watchlistQuotes.some((quote) => quote.symbol === symbol)) {
            grid.appendChild(buildUnavailableCard(symbol));
        }
    }
    updateWatchlistEmptyState();
    loadCardSparklines(sortedQuotes);
}

async function previewTicker(symbol) {
    try {
        const quote = await searchQuotes.getOne(symbol);
        if (quote.symbol) {
            showQuoteDetail(quote);
        }
    } catch (error) {
        const detail = document.getElementById('ticker-detail');
        detail.textContent = `Quote unavailable for ${symbol}. Please try again later.`;
    }
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
        renderWatchlistPills();
        return true;
    } catch (error) {
        console.error('Could not load saved symbols:', error);
        return false;
    }
}

async function toggleSearchStar(symbol, button) {
    button.disabled = true;
    await savedSymbolsReady;
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
                    const quote = await searchQuotes.getOne(symbol);
                    if (!watchlistQuotes.some((item) => item.symbol === symbol)) {
                        watchlistQuotes.push(quote);
                    }
                } catch (error) {
                    console.error('Saved symbol, but could not load its quote:', error);
                }
            }
        }

        updateSearchStars();
        renderWatchlistPills();
        renderWatchlistCards();
    } catch (error) {
        alert(error.message || 'Could not update watchlist');
    } finally {
        button.disabled = false;
    }
}

function renderWatchlistPills() {
    const list = document.getElementById('watchlist-list');
    WatchlistUi.renderPills(list, [...savedSymbols], removeSavedSymbol);
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

async function removeSavedSymbol(symbol) {
    const removed = await removeFromWatchlist(symbol);
    if (!removed) {
        return false;
    }

    watchlistQuotes = watchlistQuotes.filter((quote) => {
        return quote.symbol !== symbol;
    });
    renderWatchlistPills();
    renderWatchlistCards();
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
        const data = await fetchQuoteBatches(symbols);
        quotes = data.quotes || {};
        errors = data.errors || {};
    } catch (error) {
        for (const symbol of symbols) {
            errors[symbol] = 'Market data unavailable';
        }
    }

    DashboardShell.renderMarketFlow(
        document.getElementById('flow-items'),
        MARKET_FLOW_SYMBOLS,
        quotes,
        errors
    );
    for (const [symbol, quote] of Object.entries(quotes)) {
        searchQuotes.seed(symbol, quote);
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
            ? buildCard(quotes[symbol], symbol === selectedQuoteSymbol)
            : buildUnavailableCard(symbol, errors[symbol]));
    }
    loadCardSparklines(cardSymbols.filter((symbol) => Boolean(quotes[symbol])).map((symbol) => quotes[symbol]));

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
    searchController.init();
    savedSymbolsReady = loadSavedSymbols();
    const watchlistSort = document.getElementById('watchlist-sort');
    if (watchlistSort) {
        watchlistSort.addEventListener('change', () => {
            renderWatchlistCards();
        });
    }
    loadDashboardQuotes(savedSymbolsReady);
    DashboardShell.loadNews();
    window.setInterval(DashboardShell.loadNews, 60000);
});
