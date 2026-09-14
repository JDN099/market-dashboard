const assert = require('node:assert/strict');
const test = require('node:test');

const QuoteClient = require('../static/quote-client.js');

test('five visible results share one batch request', async () => {
    const requests = [];
    const symbols = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL'];
    const client = QuoteClient.create(async (requested) => {
        requests.push(requested);
        return {
            quotes: Object.fromEntries(requested.map((symbol) => {
                return [symbol, { symbol, price: 100 }];
            })),
            errors: {}
        };
    });

    const promises = client.getMany(symbols);
    const quotes = await Promise.all(symbols.map((symbol) => promises.get(symbol)));

    assert.equal(requests.length, 1);
    assert.deepEqual(requests[0], symbols);
    assert.equal(quotes.length, 5);
    await client.getOne('AAPL');
    assert.equal(requests.length, 1);
});

test('cached dashboard quotes are not fetched again', async () => {
    const requests = [];
    const client = QuoteClient.create(async (symbols) => {
        requests.push(symbols);
        return {
            quotes: { MSFT: { symbol: 'MSFT', price: 100 } },
            errors: {}
        };
    });
    client.seed('AAPL', { symbol: 'AAPL', price: 200 });

    const promises = client.getMany(['AAPL', 'MSFT']);
    const quotes = await Promise.all([...promises.values()]);

    assert.deepEqual(requests, [['MSFT']]);
    assert.equal(quotes[0].price, 200);
});

test('quotes are refetched when the browser cache expires', async () => {
    let currentTime = 0;
    let requestCount = 0;
    const client = QuoteClient.create(async () => {
        requestCount += 1;
        return { quotes: { AAPL: { symbol: 'AAPL', price: requestCount } } };
    }, () => currentTime, 60000);

    assert.equal((await client.getOne('AAPL')).price, 1);
    currentTime = 59999;
    assert.equal((await client.getOne('AAPL')).price, 1);
    currentTime = 60000;
    assert.equal((await client.getOne('AAPL')).price, 2);
    assert.equal(requestCount, 2);
});

test('unavailable symbols can be retried without losing successful quotes', async () => {
    let requestCount = 0;
    const client = QuoteClient.create(async () => {
        requestCount += 1;
        if (requestCount === 1) {
            return {
                quotes: { AAPL: { symbol: 'AAPL', price: 100 } },
                errors: { MSFT: 'Quote unavailable for MSFT' }
            };
        }
        return {
            quotes: { MSFT: { symbol: 'MSFT', price: 200 } },
            errors: {}
        };
    });

    const first = client.getMany(['AAPL', 'MSFT']);
    const settled = await Promise.allSettled([...first.values()]);
    assert.equal(settled[0].status, 'fulfilled');
    assert.equal(settled[1].status, 'rejected');

    assert.equal((await client.getOne('MSFT')).price, 200);
    assert.equal((await client.getOne('AAPL')).price, 100);
    assert.equal(requestCount, 2);
});
