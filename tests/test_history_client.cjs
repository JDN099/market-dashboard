const assert = require('node:assert/strict');
const test = require('node:test');

const HistoryClient = require('../static/history-client.js');

test('visible card histories use one batch and selected 1D reuses it', async () => {
    const calls = [];
    const client = HistoryClient.create(
        async () => {
            throw new Error('Single route should not be used for 1D');
        },
        async (symbols) => {
            calls.push(symbols);
            return {
                histories: Object.fromEntries(symbols.map((symbol) => {
                    return [symbol, [{ time: '2026-09-11T09:30:00-04:00', close: 100 }]];
                })),
                errors: {}
            };
        }
    );

    const histories = client.getIntradayMany(['SPY', 'QQQ', 'SPY']);
    const selected = client.getOne('SPY', '1d', '5m');

    assert.deepEqual(calls, [['SPY', 'QQQ']]);
    assert.strictEqual(selected, histories.get('SPY'));
    assert.equal((await selected)[0].close, 100);
});

test('large watchlists are split into provider-safe batches of eight', async () => {
    const calls = [];
    const symbols = Array.from({ length: 12 }, (_, index) => `S${index}`);
    const client = HistoryClient.create(async () => [], async (batch) => {
        calls.push(batch);
        return {
            histories: Object.fromEntries(batch.map((symbol) => [symbol, [{ close: 100 }]])),
            errors: {}
        };
    });

    const requests = client.getIntradayMany(symbols);
    await Promise.all(requests.values());

    assert.deepEqual(calls.map((batch) => batch.length), [8, 4]);
});

test('failed histories can be retried without refetching successful symbols', async () => {
    let calls = 0;
    const client = HistoryClient.create(async () => [], async (symbols) => {
        calls += 1;
        return {
            histories: symbols.includes('SPY') ? { SPY: [{ close: 100 }] } : { QQQ: [{ close: 99 }] },
            errors: symbols.includes('QQQ') && symbols.includes('SPY')
                ? { QQQ: 'Unavailable' }
                : {}
        };
    });

    const first = client.getIntradayMany(['SPY', 'QQQ']);
    await first.get('SPY');
    await assert.rejects(first.get('QQQ'));
    const second = client.getIntradayMany(['SPY', 'QQQ']);
    await second.get('QQQ');

    assert.equal(calls, 2);
    assert.strictEqual(first.get('SPY'), second.get('SPY'));
});
