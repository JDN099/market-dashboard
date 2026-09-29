const MarketDom = (() => {
    function safeArticleUrl(value) {
        if (typeof value !== 'string') {
            return null;
        }

        try {
            const url = new URL(value);
            if (url.protocol !== 'http:' && url.protocol !== 'https:') {
                return null;
            }
            if (!url.hostname || url.username || url.password) {
                return null;
            }
            return url.href;
        } catch (error) {
            return null;
        }
    }

    function renderNewsState(container, message, domDocument = document) {
        const state = domDocument.createElement('p');
        state.className = 'news-state';
        state.textContent = String(message);
        container.replaceChildren(state);
    }

    function createNewsArticle(article, relativeTime, domDocument = document) {
        const importance = article.importance === 'critical' || article.importance === 'watch'
            ? article.importance
            : 'normal';
        const articleElement = domDocument.createElement('article');
        articleElement.className = `news-item news-item--${importance}`;

        const metadata = domDocument.createElement('div');
        metadata.className = 'news-meta';
        const source = domDocument.createElement('span');
        source.textContent = String(article.source || 'Market news');
        const timeGroup = domDocument.createElement('div');
        timeGroup.className = 'news-time';

        if (importance !== 'normal') {
            const priority = domDocument.createElement('span');
            priority.className = `news-priority news-priority--${importance}`;
            priority.textContent = importance === 'critical' ? 'Important' : 'Watch';
            timeGroup.appendChild(priority);
        }

        const publishedAt = domDocument.createElement('time');
        publishedAt.textContent = relativeTime(article.published_at);
        timeGroup.appendChild(publishedAt);
        metadata.append(source, timeGroup);

        const headline = domDocument.createElement('p');
        const safeUrl = safeArticleUrl(article.url);
        if (safeUrl) {
            const link = domDocument.createElement('a');
            link.href = safeUrl;
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
            link.textContent = String(article.title || 'Untitled article');
            headline.appendChild(link);
        } else {
            headline.textContent = String(article.title || 'Untitled article');
        }

        const tags = domDocument.createElement('div');
        tags.className = 'news-tags';
        const symbols = Array.isArray(article.symbols) ? article.symbols : [];
        for (const symbol of symbols) {
            const tag = domDocument.createElement('span');
            tag.className = 'news-tag';
            tag.textContent = String(symbol);
            tags.appendChild(tag);
        }

        articleElement.append(metadata, headline, tags);
        return articleElement;
    }

    function renderQuoteDetail(container, quote, formatters, domDocument = document) {
        const hasChange = Number.isFinite(quote.change);
        const isPositive = hasChange && quote.change >= 0;
        const changeText = hasChange
            ? `${isPositive ? '+' : ''}${quote.change.toFixed(2)}% today`
            : 'Change unavailable';

        const heading = domDocument.createElement('div');
        heading.className = 'detail-heading';
        const identity = domDocument.createElement('div');
        const eyebrow = domDocument.createElement('span');
        eyebrow.className = 'detail-eyebrow';
        eyebrow.textContent = 'Selected instrument';
        const symbol = domDocument.createElement('h2');
        symbol.textContent = String(quote.symbol || '');
        const name = domDocument.createElement('p');
        name.textContent = String(quote.name || quote.symbol || '');
        identity.append(eyebrow, symbol, name);
        if (quote.stale) {
            const state = domDocument.createElement('span');
            state.className = 'data-state-label data-state-label--stale';
            state.textContent = 'Stale cached Twelve Data quote';
            identity.appendChild(state);
        }

        const priceGroup = domDocument.createElement('div');
        priceGroup.className = 'detail-price';
        const price = domDocument.createElement('strong');
        price.textContent = Number(quote.price).toFixed(2);
        const movement = domDocument.createElement('span');
        if (hasChange) {
            movement.className = isPositive ? 'positive' : 'negative';
        }
        movement.textContent = changeText;
        priceGroup.append(price, movement);
        heading.append(identity, priceGroup);

        const metrics = domDocument.createElement('div');
        metrics.className = 'detail-metrics';
        const rows = [
            [
                'Day range',
                `${formatters.formatMetric(quote.day_low, formatters.formatPrice)} – ${formatters.formatMetric(quote.day_high, formatters.formatPrice)}`
            ],
            [
                'Volume',
                formatters.formatMetric(quote.volume, formatters.formatCompactNumber)
            ],
            [
                quote.size_label || 'Market cap',
                quote.size_display || formatters.formatMetric(
                    quote.size_value || quote.market_cap,
                    formatters.formatCompactCurrency
                )
            ]
        ];

        for (const [label, value] of rows) {
            const metric = domDocument.createElement('div');
            const metricLabel = domDocument.createElement('span');
            metricLabel.textContent = String(label);
            const metricValue = domDocument.createElement('strong');
            metricValue.textContent = String(value);
            metric.append(metricLabel, metricValue);
            metrics.appendChild(metric);
        }

        container.replaceChildren(heading, metrics);
    }

    return {
        safeArticleUrl,
        renderNewsState,
        createNewsArticle,
        renderQuoteDetail
    };
})();

if (typeof module !== 'undefined' && module.exports) {
    module.exports = MarketDom;
}
