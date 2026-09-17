const MarketUi = (() => {
    function describeChange(change, unavailableText = 'Change unavailable') {
        if (!Number.isFinite(change)) {
            return {
                available: false,
                className: '',
                text: unavailableText
            };
        }

        const sign = change >= 0 ? '+' : '';
        return {
            available: true,
            className: change >= 0 ? 'positive' : 'negative',
            text: `${sign}${change.toFixed(2)}%`
        };
    }

    function createSparklineShell(containerClass, domDocument = document) {
        const container = domDocument.createElement('span');
        container.className = containerClass;

        const label = domDocument.createElement('span');
        label.className = 'sparkline-label';
        label.textContent = '1D';

        const graphic = domDocument.createElement('span');
        graphic.className = 'sparkline-graphic';
        graphic.appendChild(MarketCharts.createSparkline([], { domDocument }));

        container.append(label, graphic);
        return container;
    }

    return {
        createSparklineShell,
        describeChange
    };
})();

if (typeof module !== 'undefined' && module.exports) {
    module.exports = MarketUi;
}
