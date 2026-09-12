const VALID_SYMBOLS = [
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AMD', 'INTC',
    'SPY', 'QQQ', 'IWM', 'DIA', 'V', 'JPM', 'XOM', 'BRK-B', 'NFLX',
    'NQ=F', 'ES=F', 'CL=F', 'GC=F', 'BTC-USD', 'ETH-USD', '^VIX', '^TNX'
];
const MARKET_SYMBOLS = [
    'SPY',
    'QQQ',
    'IWM',
    'DIA',
    'NQ=F',
    'ES=F',
    'CL=F',
    'GC=F'
];
const MARKET_FLOW_SYMBOLS = [
    'SPY',
    'QQQ',
    'IWM',
    'DIA',
    '^VIX',
    '^TNX',
    'CL=F',
    'GC=F',
    'BTC-USD'
];
let watchlistQuotes = [];

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

    const isPositive = Number(quote.change) >= 0;
    const sign = isPositive ? '+' : '';
    detail.innerHTML = `
        <div class="detail-heading">
            <div>
                <span class="detail-eyebrow">Selected instrument</span>
                <h2>${quote.symbol}</h2>
                <p>${quote.name}</p>
            </div>
            <div class="detail-price">
                <strong>${Number(quote.price || 0).toFixed(2)}</strong>
                <span class="${isPositive ? 'positive' : 'negative'}">${sign}${Number(quote.change || 0).toFixed(2)}% today</span>
            </div>
        </div>
        <div class="detail-metrics">
            <div>
                <span>Day range</span>
                <strong>${formatMetric(quote.day_low, formatPrice)} – ${formatMetric(quote.day_high, formatPrice)}</strong>
            </div>
            <div>
                <span>Volume</span>
                <strong>${formatMetric(quote.volume, formatCompactNumber)}</strong>
            </div>
            <div>
                <span>${quote.size_label || 'Market cap'}</span>
                <strong>${formatMetric(quote.size_value || quote.market_cap, formatCompactCurrency)}</strong>
            </div>
        </div>`;
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

function renderMarketFlow(quotes) {
    const flowItems = document.getElementById('flow-items');
    if (!flowItems) {
        return;
    }

    flowItems.innerHTML = quotes.map((quote) => {
        const change = Number(quote.change || 0);
        const sign = change >= 0 ? '+' : '';
        const changeClass = change >= 0 ? 'positive' : 'negative';
        const displaySymbol = formatMarketSymbol(quote.symbol);

        return `
            <span class="flow-pill">
                <strong>${displaySymbol}</strong>
                <span class="${changeClass}">${sign}${change.toFixed(2)}%</span>
            </span>
        `;
    }).join('');
}

async function loadMarketFlow() {
    try {
        const quotes = await Promise.all(
            MARKET_FLOW_SYMBOLS.map(async (symbol) => {
                const response = await fetch(`/quote?ticker=${symbol}`);
                return response.json();
            })
        );
        renderMarketFlow(quotes);
    } catch (error) {
        const flowItems = document.getElementById('flow-items');
        if (flowItems) {
            flowItems.innerHTML = '<span class="flow-pill"><strong>Market data</strong> Unavailable</span>';
        }
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

    newsList.innerHTML = articles.map((article) => {
        const symbols = Array.isArray(article.symbols) ? article.symbols : [];
        const importance = article.importance || 'normal';
        let importanceLabel = '';
        if (importance === 'critical') {
            importanceLabel = '<span class="news-priority news-priority--critical">Important</span>';
        } else if (importance === 'watch') {
            importanceLabel = '<span class="news-priority news-priority--watch">Watch</span>';
        }
        const tags = symbols.map((symbol) => {
            return `<span class="news-tag">${symbol}</span>`;
        }).join('');
        const headline = article.url
            ? `<a href="${article.url}" target="_blank" rel="noopener noreferrer">${article.title}</a>`
            : article.title;

        return `
            <article class="news-item news-item--${importance}">
                <div class="news-meta">
                    <span>${article.source}</span>
                    <div class="news-time">
                        ${importanceLabel}
                        <time>${relativeTime(article.published_at)}</time>
                    </div>
                </div>
                <p>${headline}</p>
                <div class="news-tags">${tags}</div>
            </article>
        `;
    }).join('');
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
            newsList.innerHTML = '<p class="news-state">No market headlines are available right now.</p>';
            return;
        }

        renderNews(data.articles);
        if (status) {
            status.textContent = 'Live';
        }
    } catch (error) {
        newsList.innerHTML = `<p class="news-state">${error.message}</p>`;
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

    const changeColor = quote.change >= 0 ? 'positive' : 'negative';
    const changeSign = quote.change >= 0 ? '+' : '';

    card.addEventListener('click', () => {
        document.querySelectorAll('.ticker-card').forEach((element) => {
            element.classList.remove('selected');
        });
        card.classList.add('selected');
        showQuoteDetail(quote);
    });

    card.innerHTML = `
        <h5>${quote.symbol} - ${quote.name}</h5>
        <h3>${Number(quote.price || 0).toFixed(2)}</h3>
        <p class="${changeColor}">${changeSign}${Number(quote.change || 0).toFixed(2)}%</p>
    `;

    if (document.body.dataset.page === 'watchlist') {
        const removeButton = document.createElement('button');
        removeButton.type = 'button';
        removeButton.className = 'remove-card-btn';
        removeButton.textContent = '×';
        removeButton.addEventListener('click', async (event) => {
            event.stopPropagation();
            await removeFromWatchlist(quote.symbol);
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

function updateWatchlistEmptyState() {
    const emptyState = document.getElementById('watchlist-empty');
    const count = document.getElementById('watchlist-count');
    if (emptyState) {
        emptyState.hidden = watchlistQuotes.length > 0;
    }
    if (count) {
        const suffix = watchlistQuotes.length === 1 ? '' : 's';
        count.textContent = `${watchlistQuotes.length} saved instrument${suffix}`;
    }
}

function renderWatchlistCards() {
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

    grid.innerHTML = '';
    for (const quote of sortedQuotes) {
        grid.appendChild(buildCard(quote));
    }
    updateWatchlistEmptyState();
}

async function loadCard(symbol) {
    const response = await fetch(`/quote?ticker=${symbol}`);
    const data = await response.json();

    const existingCard = document.getElementById(`card-${data.symbol}`);
    if (existingCard) {
        return;
    }

    document.getElementById('cards-grid').appendChild(buildCard(data));
}

async function searchTicker() {
    const ticker = document.getElementById('ticker-input').value.trim().toUpperCase();

    if (!ticker) {
        document.getElementById('search-dropdown').innerHTML = '';
        return;
    }

    if (VALID_SYMBOLS.includes(ticker)) {
        await handleTickerSelection(ticker);
        document.getElementById('ticker-input').value = '';
        document.getElementById('search-dropdown').innerHTML = '';
        return;
    }

    document.getElementById('search-dropdown').innerHTML = '';
}

async function selectTicker(symbol) {
    document.getElementById('ticker-input').value = '';
    document.getElementById('search-dropdown').innerHTML = '';
    await handleTickerSelection(symbol);
}

async function previewTicker(symbol) {
    const response = await fetch(`/quote?ticker=${symbol}`);
    const quote = await response.json();
    if (response.ok && quote.symbol) {
        showQuoteDetail(quote);
    }
}

async function handleTickerSelection(symbol) {
    if (document.body.dataset.page === 'watchlist') {
        await addToWatchlist(symbol);
    } else {
        await previewTicker(symbol);
    }
}

document.getElementById('ticker-input').addEventListener('keydown', async function (e) {
    if (e.key === 'Enter') {
        const ticker = this.value.trim().toUpperCase();
        document.getElementById('search-dropdown').innerHTML = '';

        if (VALID_SYMBOLS.includes(ticker)) {
            await handleTickerSelection(ticker);
            this.value = '';
        }
    }
});

document.getElementById('ticker-input').addEventListener('input', async function () {
    const query = this.value.trim().toUpperCase();

    if (query.length === 0) {
        document.getElementById('search-dropdown').innerHTML = '';
        return;
    }

    const response = await fetch(`/search?q=${query}`);
    const results = await response.json();

    if (document.getElementById('ticker-input').value.trim() === '') {
        document.getElementById('search-dropdown').innerHTML = '';
        return;
    }

    document.getElementById('search-dropdown').innerHTML = results.map((result) => {
        return `
            <div class="dropdown-item" onclick="selectTicker('${result.symbol}')">
                <span>${result.symbol} - ${result.instrument_name}</span>
                <span class="dropdown-exchange">${result.exchange}</span>
            </div>
        `;
    }).join('');
});

document.addEventListener('click', function (event) {
    const input = document.getElementById('ticker-input');
    const dropdown = document.getElementById('search-dropdown');
    if (!input.contains(event.target) && !dropdown.contains(event.target)) {
        dropdown.innerHTML = '';
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

        list.innerHTML = symbols.map((symbol) => {
            return `
                <span class="watchlist-pill">
                    ${symbol}
                    <button type="button" data-remove="${symbol}" aria-label="Remove ${symbol}">×</button>
                </span>
            `;
        }).join('');

        list.querySelectorAll('button[data-remove]').forEach((button) => {
            button.addEventListener('click', async () => {
                const symbol = button.getAttribute('data-remove');
                await removeFromWatchlist(symbol);
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
        });
    } catch (error) {
        console.error('Could not refresh watchlist:', error);
    }
}

async function addToWatchlist(symbol) {
    const normalized = symbol.trim().toUpperCase();
    if (!normalized) return;

    const response = await fetch('/watchlist/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: normalized })
    });

    const data = await response.json();
    if (!response.ok) {
        alert(data.error || 'Unable to add symbol');
        return;
    }

    const quote = await fetch(`/quote?ticker=${normalized}`);
    const q = await quote.json();
    const grid = document.getElementById('cards-grid');
    if (q && q.symbol) {
        const existing = document.getElementById(`card-${q.symbol}`);
        if (!existing) {
            if (document.body.dataset.page === 'watchlist') {
                watchlistQuotes.push(q);
                renderWatchlistCards();
            } else {
                grid.appendChild(buildCard(q, true));
            }
        }
        showQuoteDetail(q);
    }
    await refreshWatchlistList();
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
    }
}

async function loadDefaultCards() {
    const page = document.body.dataset.page;
    const isMarketsPage = page === 'markets';
    const isWatchlistPage = page === 'watchlist';

    try {
        if (isWatchlistPage) {
            const response = await fetch('/watchlist/quotes');
            const quotes = await response.json();

            watchlistQuotes = Array.isArray(quotes) ? quotes : [];
            renderWatchlistCards();
            return;
        }
    } catch (error) {
        if (isWatchlistPage) {
            watchlistQuotes = [];
            renderWatchlistCards();
            return;
        }
        // fall through to default symbols
    }

    const defaults = isMarketsPage
        ? MARKET_SYMBOLS
        : ['SPY', 'QQQ', 'AAPL', 'MSFT', 'NVDA', 'TSLA'];
    const results = await Promise.all(
        defaults.map(async (symbol) => {
            const response = await fetch(`/quote?ticker=${symbol}`);
            return response.json();
        })
    );

    const grid = document.getElementById('cards-grid');
    grid.innerHTML = '';

    for (const data of results) {
        grid.appendChild(buildCard(data));
    }

    if (results[0]) {
        showQuoteDetail(results[0]);
    }
}

document.addEventListener('DOMContentLoaded', function () {
    const watchlistSort = document.getElementById('watchlist-sort');
    if (watchlistSort) {
        watchlistSort.addEventListener('change', () => {
            renderWatchlistCards();
        });
    }
    refreshWatchlistList();
    loadDefaultCards();
    loadMarketFlow();
    loadNews();
    window.setInterval(loadNews, 60000);
});
