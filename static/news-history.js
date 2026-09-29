let selectedRange = '24h';
let currentPage = 1;
const MARKET_CONFIG = JSON.parse(document.getElementById('market-config').textContent);

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

function formatMarketSymbol(symbol) {
    const labels = {
        'BTC/USD': 'BTC/USD',
        'EUR/USD': 'EUR/USD',
        'GLD': 'GLD',
        'USO': 'USO'
    };

    return labels[symbol] || symbol;
}

async function loadNewsHistory(append = false) {
    const list = document.getElementById('news-history-list');
    const loadMoreButton = document.getElementById('load-more-news');
    if (!append) {
        MarketDom.renderNewsState(list, 'Loading news history…');
    }

    try {
        const response = await fetch(`/news?range=${selectedRange}&page=${currentPage}`);
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Unable to load market news');
        }

        const articles = Array.isArray(data.articles) ? data.articles : [];
        if (!append) {
            list.replaceChildren();
        }
        for (const article of articles) {
            list.appendChild(MarketDom.createNewsArticle(article, relativeTime));
        }
        if (!append && articles.length === 0) {
            MarketDom.renderNewsState(list, 'No matching news is available.');
        }
        loadMoreButton.hidden = articles.length < 3;
    } catch (error) {
        MarketDom.renderNewsState(list, error.message);
        loadMoreButton.hidden = true;
    }
}

async function loadLatestNews() {
    const list = document.getElementById('latest-news-list');
    const status = document.getElementById('latest-news-status');

    try {
        const response = await fetch('/news');
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Unable to load market news');
        }

        const articles = Array.isArray(data.articles) ? data.articles : [];
        list.replaceChildren();
        for (const article of articles) {
            list.appendChild(MarketDom.createNewsArticle(article, relativeTime));
        }
        if (articles.length === 0) {
            MarketDom.renderNewsState(list, 'No market headlines are available right now.');
        }
        status.textContent = 'Delayed';
    } catch (error) {
        MarketDom.renderNewsState(list, error.message);
        status.textContent = 'Offline';
    }
}

async function loadMarketFlow() {
    const flowItems = document.getElementById('news-flow-items');
    const symbols = MARKET_CONFIG.market_flow_symbols;
    if (!flowItems) {
        return;
    }

    try {
        const response = await fetch(`/api/quotes?symbols=${encodeURIComponent(symbols.join(','))}`);
        if (!response.ok) {
            throw new Error('Market data unavailable');
        }
        const data = await response.json();
        flowItems.replaceChildren();
        for (const symbol of symbols) {
            const quote = data.quotes[symbol];
            const pill = document.createElement('span');
            pill.className = 'flow-pill';
            const label = document.createElement('strong');
            label.textContent = formatMarketSymbol(symbol);
            const movement = document.createElement('span');
            if (quote && Number.isFinite(quote.change)) {
                movement.className = quote.change >= 0 ? 'positive' : 'negative';
                const value = `${quote.change >= 0 ? '+' : ''}${quote.change.toFixed(2)}%`;
                movement.textContent = quote.stale ? `${value} · Stale` : value;
                movement.title = quote.stale
                    ? 'Stale cached Twelve Data quote'
                    : quote.change_basis || 'Daily change';
            } else {
                movement.textContent = data.errors?.[symbol] || 'Unavailable';
            }
            pill.append(label, movement);
            flowItems.appendChild(pill);
        }
    } catch (error) {
        flowItems.textContent = 'Market data unavailable';
    }
}

document.querySelectorAll('.news-filter').forEach((button) => {
    button.addEventListener('click', () => {
        selectedRange = button.dataset.range;
        currentPage = 1;
        document.querySelectorAll('.news-filter').forEach((filter) => {
            filter.classList.toggle('active', filter === button);
        });
        loadNewsHistory();
    });
});

document.getElementById('load-more-news').addEventListener('click', () => {
    currentPage += 1;
    loadNewsHistory(true);
});

loadNewsHistory();
loadLatestNews();
loadMarketFlow();
