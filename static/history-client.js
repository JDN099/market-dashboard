const HistoryClient = (() => {
    function create(fetchOne, fetchIntradayBatch, now = Date.now, ttlMilliseconds = 21600000) {
        const cache = new Map();

        function cacheKey(symbol, period, interval) {
            return `${symbol}:${period}:${interval}`;
        }

        function cachedRequest(key) {
            const cached = cache.get(key);
            if (cached && now() - cached.createdAt < ttlMilliseconds) {
                return cached.request;
            }
            return null;
        }

        function remember(key, request) {
            cache.set(key, {
                createdAt: now(),
                request
            });
            request.catch(() => {
                if (cache.get(key)?.request === request) {
                    cache.delete(key);
                }
            });
            return request;
        }

        function getIntradayMany(symbols) {
            const uniqueSymbols = [...new Set(symbols)];
            const missing = uniqueSymbols.filter((symbol) => {
                return !cachedRequest(cacheKey(symbol, '1d', '5m'));
            });

            for (let start = 0; start < missing.length; start += 8) {
                const batch = missing.slice(start, start + 8);
                const batchRequest = fetchIntradayBatch(batch);
                for (const symbol of batch) {
                    const key = cacheKey(symbol, '1d', '5m');
                    const request = batchRequest.then((data) => {
                        const points = data.histories && data.histories[symbol];
                        if (!points) {
                            throw new Error((data.errors && data.errors[symbol]) || 'Price history unavailable');
                        }
                        return points;
                    });
                    remember(key, request);
                }
            }

            return new Map(uniqueSymbols.map((symbol) => {
                const key = cacheKey(symbol, '1d', '5m');
                return [symbol, cache.get(key).request];
            }));
        }

        function getOne(symbol, period, interval) {
            if (period === '1d' && interval === '5m') {
                return getIntradayMany([symbol]).get(symbol);
            }

            const key = cacheKey(symbol, period, interval);
            const cached = cachedRequest(key);
            if (cached) {
                return cached;
            }

            return remember(key, fetchOne(symbol, period, interval));
        }

        return {
            getOne,
            getIntradayMany
        };
    }

    return { create };
})();

if (typeof module !== 'undefined' && module.exports) {
    module.exports = HistoryClient;
}
