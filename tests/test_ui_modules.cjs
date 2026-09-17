const assert = require('node:assert/strict');
const test = require('node:test');

global.MarketCharts = {
    createSparkline() {
        return new FakeElement('svg');
    }
};

const MarketUi = require('../static/market-ui.js');
const SearchController = require('../static/search.js');
const WatchlistUi = require('../static/watchlist-ui.js');

class FakeElement {
    constructor(tagName) {
        this.tagName = tagName;
        this.attributes = {};
        this.children = [];
        this.className = '';
        this.dataset = {};
        this.hidden = false;
        this.listeners = {};
        this.textContent = '';
        this.value = '';
    }

    addEventListener(name, listener) {
        this.listeners[name] = listener;
    }

    append(...children) {
        this.children.push(...children);
    }

    appendChild(child) {
        this.children.push(child);
    }

    contains(target) {
        return target === this;
    }

    replaceChildren(...children) {
        this.children = [...children];
        this.textContent = '';
    }

    setAttribute(name, value) {
        this.attributes[name] = value;
    }
}

function createDocument(elements = {}) {
    return {
        listeners: {},
        addEventListener(name, listener) {
            this.listeners[name] = listener;
        },
        createElement(tagName) {
            return new FakeElement(tagName);
        },
        getElementById(id) {
            return elements[id];
        }
    };
}

test('change descriptions share consistent text and color classes', () => {
    assert.deepEqual(MarketUi.describeChange(1.25), {
        available: true,
        className: 'positive',
        text: '+1.25%'
    });
    assert.deepEqual(MarketUi.describeChange(-0.5), {
        available: true,
        className: 'negative',
        text: '-0.50%'
    });
    assert.deepEqual(MarketUi.describeChange(null), {
        available: false,
        className: '',
        text: 'Change unavailable'
    });
});

test('sparkline shell provides the shared 1D label and chart container', () => {
    const domDocument = createDocument();
    const shell = MarketUi.createSparklineShell('card-sparkline', domDocument);

    assert.equal(shell.className, 'card-sparkline');
    assert.equal(shell.children[0].className, 'sparkline-label');
    assert.equal(shell.children[0].textContent, '1D');
    assert.equal(shell.children[1].className, 'sparkline-graphic');
    assert.equal(shell.children[1].children[0].tagName, 'svg');
});

test('watchlist UI renders its summary and delegates removal', () => {
    const container = new FakeElement('div');
    const emptyState = new FakeElement('div');
    const count = new FakeElement('span');
    const removed = [];
    const domDocument = createDocument();

    WatchlistUi.renderSummary(emptyState, count, 2);
    WatchlistUi.renderPills(container, ['AAPL', 'MSFT'], (symbol) => {
        removed.push(symbol);
    }, domDocument);

    assert.equal(emptyState.hidden, true);
    assert.equal(count.textContent, '2 saved instruments');
    assert.equal(container.children.length, 2);
    container.children[0].children[1].listeners.click();
    assert.deepEqual(removed, ['AAPL']);
});

test('search button and Enter key use the same submission behavior', async () => {
    const input = new FakeElement('input');
    const button = new FakeElement('button');
    const dropdown = new FakeElement('div');
    const domDocument = createDocument({
        'ticker-input': input,
        'ticker-search-button': button,
        'search-dropdown': dropdown
    });
    const previews = [];
    const controller = SearchController.create({
        validSymbols: ['SPY'],
        quoteClient: {},
        historyClient: {},
        loadIntradaySparkline() {},
        async onPreview(symbol) {
            previews.push(symbol);
        },
        onToggleStar() {},
        onResultsRendered() {},
        domDocument
    });

    controller.init();
    input.value = 'spy';
    await button.listeners.click();
    input.value = 'SPY';
    await input.listeners.keydown({ key: 'Enter' });

    assert.deepEqual(previews, ['SPY', 'SPY']);
    assert.equal(input.value, '');
});
