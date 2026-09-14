const QuoteClient = (() => {
    function create(fetchQuotes, now = Date.now, ttlMilliseconds = 60000) {
        const cache = new Map();

        function seed(symbol, quote) {
            cache.set(symbol, {
                createdAt: now(),
                promise: Promise.resolve(quote)
            });
        }

        function getMany(symbols) {
            const uniqueSymbols = [...new Set(symbols)];
            const missing = uniqueSymbols.filter((symbol) => {
                const cached = cache.get(symbol);
                return !cached || now() - cached.createdAt >= ttlMilliseconds;
            });

            if (missing.length > 0) {
                const batchPromise = fetchQuotes(missing);
                for (const symbol of missing) {
                    const promise = batchPromise.then((data) => {
                        const quote = data.quotes && data.quotes[symbol];
                        if (!quote) {
                            throw new Error((data.errors && data.errors[symbol]) || 'Quote unavailable');
                        }
                        return quote;
                    });
                    cache.set(symbol, {
                        createdAt: now(),
                        promise
                    });
                    promise.catch(() => {
                        if (cache.get(symbol)?.promise === promise) {
                            cache.delete(symbol);
                        }
                    });
                }
            }

            return new Map(uniqueSymbols.map((symbol) => {
                return [symbol, cache.get(symbol).promise];
            }));
        }

        function getOne(symbol) {
            return getMany([symbol]).get(symbol);
        }

        return {
            seed,
            getMany,
            getOne
        };
    }

    return { create };
})();

if (typeof module !== 'undefined' && module.exports) {
    module.exports = QuoteClient;
}
