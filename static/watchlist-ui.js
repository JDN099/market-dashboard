const WatchlistUi = (() => {
    function renderSummary(emptyState, count, size) {
        if (emptyState) {
            emptyState.hidden = size > 0;
        }
        if (count) {
            const suffix = size === 1 ? '' : 's';
            count.textContent = `${size} saved instrument${suffix}`;
        }
    }

    function renderPills(container, symbols, onRemove, domDocument = document) {
        if (!container) {
            return;
        }

        container.replaceChildren();
        for (const symbol of symbols) {
            const pill = domDocument.createElement('span');
            pill.className = 'watchlist-pill';

            const label = domDocument.createElement('span');
            label.textContent = symbol;

            const button = domDocument.createElement('button');
            button.type = 'button';
            button.setAttribute('aria-label', `Remove ${symbol}`);
            button.textContent = '×';
            button.addEventListener('click', () => {
                onRemove(symbol);
            });

            pill.append(label, button);
            container.appendChild(pill);
        }
    }

    return {
        renderPills,
        renderSummary
    };
})();

if (typeof module !== 'undefined' && module.exports) {
    module.exports = WatchlistUi;
}
