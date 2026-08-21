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