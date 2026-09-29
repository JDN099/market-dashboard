const DashboardShell = (() => {
    function readMarketConfig(domDocument = document) {
        const configElement = domDocument.getElementById('market-config');
        if (!configElement) {
            return { market_flow_symbols: [] };
        }
        return JSON.parse(configElement.textContent);
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

    function relativeTime(timestamp, now = Date.now()) {
        const publishedAt = new Date(timestamp).getTime();
        if (Number.isNaN(publishedAt)) {
            return 'Recently';
        }

        const minutes = Math.max(0, Math.floor((now - publishedAt) / 60000));
        if (minutes < 1) {
            return 'Just now';
        }
        if (minutes < 60) {
            return `${minutes}m ago`;
        }
        if (minutes < 1440) {
            return `${Math.floor(minutes / 60)}h ago`;
        }
        return `${Math.floor(minutes / 1440)}d ago`;
    }

    function renderMarketFlow(container, symbols, quotes, errors, domDocument = document) {
        if (!container) {
            return;
        }
        container.replaceChildren();
        for (const symbol of symbols) {
            const pill = domDocument.createElement('span');
            pill.className = 'flow-pill';
            const label = domDocument.createElement('strong');
            label.textContent = formatMarketSymbol(symbol);
            const movement = domDocument.createElement('span');
            const quote = quotes[symbol];
            if (quote) {
                const display = MarketUi.describeChange(quote.change, 'Unavailable');
                movement.className = display.className;
                movement.textContent = quote.stale ? `${display.text} · Stale` : display.text;
                movement.title = quote.stale
                    ? 'Stale cached Twelve Data quote'
                    : quote.change_basis || 'Daily change';
            } else {
                movement.textContent = 'Unavailable';
                movement.title = errors[symbol] || 'Change unavailable';
            }
            pill.append(label, movement);
            container.appendChild(pill);
        }
    }

    async function loadMarketFlow(config, domDocument = document) {
        const container = domDocument.getElementById('flow-items');
        const symbols = config.market_flow_symbols || [];
        if (!container || symbols.length === 0) {
            return;
        }

        try {
            const response = await fetch(`/api/quotes?symbols=${encodeURIComponent(symbols.join(','))}`);
            const data = await response.json();
            renderMarketFlow(container, symbols, data.quotes || {}, data.errors || {}, domDocument);
        } catch (error) {
            renderMarketFlow(container, symbols, {}, {}, domDocument);
        }
    }

    async function loadNews(domDocument = document) {
        const container = domDocument.getElementById('news-list');
        const status = domDocument.getElementById('news-status');
        if (!container) {
            return;
        }

        try {
            const response = await fetch('/news');
            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.error || 'Unable to load market news');
            }
            if (!Array.isArray(data.articles) || data.articles.length === 0) {
                MarketDom.renderNewsState(container, 'No market headlines are available right now.', domDocument);
                return;
            }

            const articles = data.articles.map((article) => {
                return MarketDom.createNewsArticle(article, relativeTime, domDocument);
            });
            container.replaceChildren(...articles);
            if (status) {
                status.textContent = 'Delayed';
            }
        } catch (error) {
            MarketDom.renderNewsState(container, error.message, domDocument);
            if (status) {
                status.textContent = 'Offline';
            }
        }
    }

    function init(domDocument = document) {
        const config = readMarketConfig(domDocument);
        loadMarketFlow(config, domDocument);
        loadNews(domDocument);
        window.setInterval(() => {
            loadNews(domDocument);
        }, 60000);
    }

    return {
        formatMarketSymbol,
        relativeTime,
        renderMarketFlow,
        loadNews,
        init
    };
})();

if (typeof module !== 'undefined' && module.exports) {
    module.exports = DashboardShell;
}
