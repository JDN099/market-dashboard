const MarketCharts = (() => {
    function formatHistoryDate(value, period) {
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return '';
        }
        if (period === '1d') {
            return date.toLocaleString('en-US', {
                month: 'short',
                day: 'numeric',
                hour: 'numeric',
                minute: '2-digit',
                timeZone: 'America/New_York',
                timeZoneName: 'short'
            });
        }
        return date.toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric',
            timeZone: 'UTC'
        });
    }

    function calculatePeriodChange(points) {
        if (!Array.isArray(points) || points.length < 2) {
            return null;
        }

        const prices = points.map((point) => Number(point.close));
        if (prices.some((price) => !Number.isFinite(price) || price <= 0)) {
            return null;
        }

        const first = prices[0];
        const last = prices[prices.length - 1];
        return Number((((last - first) / first) * 100).toFixed(2));
    }

    function formatPeriodChange(change) {
        const sign = change > 0 ? '+' : '';
        return `${sign}${change.toFixed(2)}%`;
    }

    function createSparkline(values, { dailyChange = null, domDocument = document } = {}) {
        const prices = Array.isArray(values) ? values.map(Number) : [];
        if (prices.length < 2 || prices.some((price) => !Number.isFinite(price))) {
            const empty = domDocument.createElement('span');
            empty.className = 'dropdown-chart-empty';
            empty.textContent = '—';
            return empty;
        }

        const width = 86;
        const height = 30;
        const minimum = Math.min(...prices);
        const maximum = Math.max(...prices);
        const spread = maximum - minimum || 1;
        const coordinates = prices.map((price, index) => {
            const x = 2 + (index / (prices.length - 1)) * (width - 4);
            const y = height - 3 - ((price - minimum) / spread) * (height - 6);
            return `${x.toFixed(1)},${y.toFixed(1)}`;
        });

        const svg = domDocument.createElementNS('http://www.w3.org/2000/svg', 'svg');
        const direction = Number.isFinite(dailyChange)
            ? (dailyChange >= 0 ? 'positive' : 'negative')
            : '';
        svg.setAttribute('class', `dropdown-chart ${direction}`.trim());
        svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
        svg.setAttribute('aria-label', 'One-day intraday price trend; color follows daily percentage change');
        svg.setAttribute('role', 'img');

        const line = domDocument.createElementNS('http://www.w3.org/2000/svg', 'polyline');
        line.setAttribute('points', coordinates.join(' '));
        svg.appendChild(line);
        return svg;
    }

    function createHistoryChart(points, symbol, periodLabel, { domDocument = document } = {}) {
        const prices = Array.isArray(points) ? points.map((point) => Number(point.close)) : [];
        const periodChange = calculatePeriodChange(points);
        if (periodChange === null) {
            return null;
        }

        const width = 800;
        const height = 150;
        const inset = 5;
        const minimum = Math.min(...prices);
        const maximum = Math.max(...prices);
        const padding = (maximum - minimum || maximum * 0.01 || 1) * 0.12;
        const lowerBound = minimum - padding;
        const spread = maximum - minimum + 2 * padding;
        const coordinates = prices.map((price, index) => {
            const x = inset + (index / (prices.length - 1)) * (width - 2 * inset);
            const y = height - inset - ((price - lowerBound) / spread) * (height - 2 * inset);
            return `${x.toFixed(1)},${y.toFixed(1)}`;
        });
        const direction = periodChange > 0
            ? 'positive'
            : (periodChange < 0 ? 'negative' : '');

        const svg = domDocument.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('class', `history-chart ${direction}`.trim());
        svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
        svg.setAttribute('preserveAspectRatio', 'none');
        svg.setAttribute('role', 'img');
        svg.setAttribute(
            'aria-label',
            `${symbol} ${periodLabel} closing-price history, ${formatPeriodChange(periodChange)} over selected range`
        );

        const line = domDocument.createElementNS('http://www.w3.org/2000/svg', 'polyline');
        line.setAttribute('points', coordinates.join(' '));
        svg.appendChild(line);
        return svg;
    }

    return {
        formatHistoryDate,
        calculatePeriodChange,
        formatPeriodChange,
        createSparkline,
        createHistoryChart
    };
})();

if (typeof module !== 'undefined' && module.exports) {
    module.exports = MarketCharts;
}
