let selectedRange = '24h';
let currentPage = 1;

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

function articleMarkup(article) {
    const importance = article.importance || 'normal';
    const symbols = Array.isArray(article.symbols) ? article.symbols : [];
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
                <div class="news-time">${importanceLabel}<time>${relativeTime(article.published_at)}</time></div>
            </div>
            <p>${headline}</p>
            <div class="news-tags">${tags}</div>
        </article>`;
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

async function loadNewsHistory(append = false) {
    const list = document.getElementById('news-history-list');
    const loadMoreButton = document.getElementById('load-more-news');
    if (!append) {
        list.innerHTML = '<p class="news-state">Loading news history…</p>';
    }

    try {
        const response = await fetch(`/news?range=${selectedRange}&page=${currentPage}`);
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Unable to load market news');
        }

        const articles = Array.isArray(data.articles) ? data.articles : [];
        const markup = articles.map((article) => {
            return articleMarkup(article);
        }).join('');
        if (append) {
            list.insertAdjacentHTML('beforeend', markup);
        } else {
            list.innerHTML = markup || '<p class="news-state">No matching news is available.</p>';
        }
        loadMoreButton.hidden = articles.length < 3;
    } catch (error) {
        list.innerHTML = `<p class="news-state">${error.message}</p>`;
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

        list.innerHTML = data.articles.map((article) => {
            return articleMarkup(article);
        }).join('');
        status.textContent = 'Live';
    } catch (error) {
        list.innerHTML = `<p class="news-state">${error.message}</p>`;
        status.textContent = 'Offline';
    }
}

async function loadMarketFlow() {
    const flowItems = document.getElementById('news-flow-items');
    const symbols = [
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
    if (!flowItems) {
        return;
    }

    try {
        const quotes = await Promise.all(
            symbols.map(async (symbol) => {
                const response = await fetch(`/quote?ticker=${symbol}`);
                return response.json();
            })
        );

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
    } catch (error) {
        flowItems.innerHTML = '<span class="flow-pill"><strong>Market data</strong> Unavailable</span>';
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
