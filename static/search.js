const SearchController = (() => {
    function create({
        validSymbols,
        quoteClient,
        historyClient,
        loadIntradaySparkline,
        onPreview,
        onToggleStar,
        onResultsRendered,
        domDocument = document
    }) {
        let requestId = 0;
        let searchTimer;

        function getElements() {
            return {
                button: domDocument.getElementById('ticker-search-button'),
                dropdown: domDocument.getElementById('search-dropdown'),
                input: domDocument.getElementById('ticker-input')
            };
        }

        function clearResults() {
            clearTimeout(searchTimer);
            requestId += 1;
            getElements().dropdown.replaceChildren();
        }

        async function submit() {
            const { dropdown, input } = getElements();
            clearTimeout(searchTimer);
            requestId += 1;
            const ticker = input.value.trim().toUpperCase();

            if (!ticker) {
                dropdown.replaceChildren();
                return;
            }

            if (validSymbols.includes(ticker)) {
                await onPreview(ticker);
                input.value = '';
            }
            dropdown.replaceChildren();
        }

        async function select(symbol) {
            const { dropdown, input } = getElements();
            requestId += 1;
            input.value = '';
            dropdown.replaceChildren();
            await onPreview(symbol);
        }

        function renderResults(results, resultRequestId) {
            const { dropdown } = getElements();
            dropdown.replaceChildren();

            if (results.length === 0) {
                const empty = domDocument.createElement('div');
                empty.className = 'dropdown-empty';
                empty.textContent = 'No supported symbols found';
                dropdown.appendChild(empty);
                return;
            }

            const visibleResults = results.slice(0, 5);
            const symbols = visibleResults.map((result) => {
                return result.symbol;
            });
            const quotePromises = quoteClient.getMany(symbols);
            const intradayPromises = historyClient.getIntradayMany(symbols);

            for (const result of visibleResults) {
                const row = domDocument.createElement('div');
                row.className = 'dropdown-item';

                const star = domDocument.createElement('button');
                star.type = 'button';
                star.className = 'dropdown-star';
                star.dataset.symbol = result.symbol;
                star.addEventListener('click', () => {
                    onToggleStar(result.symbol, star);
                });

                const selectButton = domDocument.createElement('button');
                selectButton.type = 'button';
                selectButton.className = 'dropdown-select';
                selectButton.addEventListener('click', () => {
                    select(result.symbol);
                });

                const identity = domDocument.createElement('span');
                identity.className = 'dropdown-identity';
                const symbol = domDocument.createElement('strong');
                symbol.textContent = result.symbol;
                const name = domDocument.createElement('small');
                name.textContent = result.instrument_name;
                identity.append(symbol, name);

                const quoteLabel = domDocument.createElement('span');
                quoteLabel.className = 'dropdown-quote';
                quoteLabel.textContent = 'Loading…';

                const chart = MarketUi.createSparklineShell('dropdown-chart-wrap', domDocument);
                selectButton.append(identity, quoteLabel, chart);
                row.append(star, selectButton);
                dropdown.appendChild(row);

                loadIntradaySparkline(
                    result.symbol,
                    chart,
                    intradayPromises.get(result.symbol),
                    quotePromises.get(result.symbol)
                );

                quotePromises.get(result.symbol).then((quote) => {
                    if (resultRequestId !== requestId || !row.isConnected) {
                        return;
                    }

                    if (Number(quote.price) > 0) {
                        const display = MarketUi.describeChange(quote.change);
                        quoteLabel.replaceChildren();
                        const price = domDocument.createElement('strong');
                        price.textContent = Number(quote.price).toFixed(2);
                        const movement = domDocument.createElement('small');
                        movement.className = display.className;
                        movement.textContent = display.text;
                        movement.title = display.available
                            ? quote.change_basis || 'Daily change'
                            : 'Change unavailable';
                        quoteLabel.append(price, movement);
                    } else {
                        quoteLabel.textContent = 'Data unavailable';
                    }
                }).catch(() => {
                    if (resultRequestId === requestId && row.isConnected) {
                        quoteLabel.textContent = 'Data unavailable';
                    }
                });
            }

            onResultsRendered();
        }

        async function runSearch() {
            const { dropdown, input } = getElements();
            const query = input.value.trim().toUpperCase();
            const currentRequestId = ++requestId;

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
                if (currentRequestId === requestId) {
                    renderResults(results, currentRequestId);
                }
            } catch (error) {
                if (currentRequestId === requestId) {
                    dropdown.textContent = 'Search unavailable';
                }
            }
        }

        function init() {
            const { button, dropdown, input } = getElements();
            button.addEventListener('click', submit);
            input.addEventListener('keydown', async (event) => {
                if (event.key === 'Enter') {
                    await submit();
                }
            });
            input.addEventListener('input', () => {
                clearTimeout(searchTimer);
                requestId += 1;
                if (!input.value.trim()) {
                    dropdown.replaceChildren();
                    return;
                }
                searchTimer = setTimeout(runSearch, 250);
            });
            domDocument.addEventListener('click', (event) => {
                if (!input.contains(event.target) && !dropdown.contains(event.target)) {
                    clearResults();
                }
            });
        }

        return {
            init,
            submit
        };
    }

    return { create };
})();

if (typeof module !== 'undefined' && module.exports) {
    module.exports = SearchController;
}
