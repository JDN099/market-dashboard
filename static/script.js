const VALID_SYMBOLS = [
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AMD', 'INTC',
    'SPY', 'QQQ', 'IWM', 'DIA', 'V', 'JPM', 'XOM', 'BRK-B', 'NFLX',
    'NQ=F', 'ES=F', 'CL=F', 'GC=F', 'BTC-USD', 'ETH-USD'
];

function buildCard(quote, selected = false) {
    const card = document.createElement('div');
    card.className = `ticker-card${selected ? ' selected' : ''}`;
    card.id = `card-${quote.symbol}`;
    card.dataset.symbol = quote.symbol;

    const changeColor = quote.change >= 0 ? 'positive' : 'negative';
    const changeSign = quote.change >= 0 ? '+' : '';

    const removeButton = document.createElement('button');
    removeButton.type = 'button';
    removeButton.className = 'remove-card-btn';
    removeButton.textContent = '?';
    removeButton.addEventListener('click', async (event) => {
        event.stopPropagation();
        await removeFromWatchlist(quote.symbol);
        await refreshWatchlistList();
        card.remove();
    });

    card.addEventListener('click', () => {
        document.querySelectorAll('.ticker-card').forEach((el) => el.classList.remove('selected'));
        card.classList.add('selected');
    });

    card.innerHTML = `
        <h5>${quote.symbol} - ${quote.name}</h5>
        <h3>${Number(quote.price || 0).toFixed(2)}</h3>
        <p class="${changeColor}">${changeSign}${Number(quote.change || 0).toFixed(2)}%</p>
    `;

    card.appendChild(removeButton);
    return card;
}

async function loadCard(symbol) {
    const response = await fetch(`/quote?ticker=${symbol}`);
    const data = await response.json();

    const existingCard = document.getElementById(`card-${data.symbol}`);
    if (existingCard) return;

    document.getElementById('cards-grid').appendChild(buildCard(data));
}

async function searchTicker() {
    const ticker = document.getElementById('ticker-input').value.trim().toUpperCase();

    if (!ticker || !VALID_SYMBOLS.includes(ticker)) {
        document.getElementById('search-dropdown').innerHTML = '';
        return;
    }

    await loadCard(ticker);
}

function selectTicker(symbol) {
    document.getElementById('ticker-input').value = symbol;
    document.getElementById('search-dropdown').innerHTML = '';
    searchTicker();
}

document.getElementById('ticker-input').addEventListener('keydown', function (e) {
    if (e.key === 'Enter') {
        const ticker = this.value.trim().toUpperCase();
        const matches = VALID_SYMBOLS.includes(ticker);

        document.getElementById('search-dropdown').innerHTML = '';

        if (matches) {
            searchTicker();
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

    document.getElementById('search-dropdown').innerHTML = results.map(r => `
        <div class="dropdown-item" onclick="selectTicker('${r.symbol}')">
            <span>${r.symbol} - ${r.instrument_name}</span>
            <span class="dropdown-exchange">${r.exchange}</span>
        </div>
    `).join('');
});

document.addEventListener('click', function (event) {
    const input = document.getElementById('ticker-input');
    const dropdown = document.getElementById('search-dropdown');
    if (!input.contains(event.target) && !dropdown.contains(event.target)) {
        dropdown.innerHTML = '';
    }
});

async function refreshWatchlistList() {
    try {
        const response = await fetch('/watchlist');
        const data = await response.json();
        const symbols = Array.isArray(data.watchlist) ? data.watchlist : [];
        const list = document.getElementById('watchlist-list');

        if (!list) return;

        list.innerHTML = symbols.map((symbol) => `
            <span class="watchlist-pill">
                ${symbol}
                <button type="button" data-remove="${symbol}" aria-label="Remove ${symbol}">?</button>
            </span>
        `).join('');

        list.querySelectorAll('button[data-remove]').forEach((button) => {
            button.addEventListener('click', async () => {
                const symbol = button.getAttribute('data-remove');
                await removeFromWatchlist(symbol);
                await refreshWatchlistList();
                const card = document.getElementById(`card-${symbol}`);
                if (card) card.remove();
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
            grid.appendChild(buildCard(q, true));
        }
    }
    await refreshWatchlistList();
}

async function removeFromWatchlist(symbol) {
    if (!symbol) return;

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

document.getElementById('watchlist-form').addEventListener('submit', async function (event) {
    event.preventDefault();
    const value = document.getElementById('watchlist-input').value.trim();
    if (!value) return;
    await addToWatchlist(value);
    document.getElementById('watchlist-input').value = '';
});

async function renderWatchlistCards() {
    try {
        const response = await fetch('/watchlist/quotes');
        const quotes = await response.json();

        const grid = document.getElementById('cards-grid');
        if (!grid) return;

        grid.innerHTML = '';

        for (const quote of quotes) {
            grid.appendChild(buildCard(quote, true));
        }
    } catch (error) {
        console.error('Failed to load watchlist quotes:', error);
    }
}

async function loadDefaultCards() {
    try {
        const response = await fetch('/watchlist/quotes');
        const quotes = await response.json();

        if (Array.isArray(quotes) && quotes.length > 0) {
            const grid = document.getElementById('cards-grid');
            grid.innerHTML = '';
            for (const quote of quotes) {
                grid.appendChild(buildCard(quote));
            }
            return;
        }
    } catch (error) {
        // fall through to default symbols
    }

    const defaults = ['SPY', 'QQQ', 'AAPL', 'MSFT', 'NVDA', 'TSLA'];
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
}

document.addEventListener('DOMContentLoaded', function () {
    refreshWatchlistList();
    loadDefaultCards();
});
