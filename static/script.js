async function searchTicker() {
    const ticker = document.getElementById('ticker-input').value.toUpperCase();
    const response = await fetch(`/quote?ticker=${ticker}`);
    const data = await response.json();

    let changeColor;
    if (data.change >= 0) {
        changeColor = 'positive';
    } else {
        changeColor = 'negative';
    }

    let changeSign;
    if (data.change >= 0) {
        changeSign = '+';
    } else {
        changeSign = '';
    }

    document.getElementById('ticker-result').innerHTML = `
        <div class="ticker-card">
            <h5>${data.symbol} - ${data.name}</h5>
            <h3>${data.price.toFixed(2)}</h3>
            <p class="${changeColor}">${changeSign}${data.change.toFixed(2)}%</p>
        </div>
    `;
}

function selectTicker(symbol) {
    document.getElementById('ticker-input').value = symbol;
    document.getElementById('search-dropdown').innerHTML = '';
    searchTicker();
}

document.getElementById('ticker-input').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
        document.getElementById('search-dropdown').innerHTML = '';
        searchTicker();
    }
});

document.getElementById('ticker-input').addEventListener('input', async function() {
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

document.addEventListener('click', function(e) {
    if (!document.getElementById('ticker-input').contains(e.target) &&
        !document.getElementById('search-dropdown').contains(e.target)) {
        document.getElementById('search-dropdown').innerHTML = '';
    }
});