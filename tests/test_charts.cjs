const assert = require('node:assert/strict');
const test = require('node:test');

const MarketCharts = require('../static/charts.js');

class FakeElement {
    constructor(tagName) {
        this.tagName = tagName;
        this.attributes = {};
        this.children = [];
        this.textContent = '';
        this.className = '';
    }

    setAttribute(name, value) {
        this.attributes[name] = value;
    }

    appendChild(child) {
        this.children.push(child);
    }
}

const fakeDocument = {
    createElement(tagName) {
        return new FakeElement(tagName);
    },
    createElementNS(_namespace, tagName) {
        return new FakeElement(tagName);
    }
};

test('sparkline renders supplied intraday prices', () => {
    const chart = MarketCharts.createSparkline([100, 102, 101, 104, 105], {
        dailyChange: 1.2,
        domDocument: fakeDocument
    });

    assert.equal(chart.tagName, 'svg');
    assert.match(chart.attributes.class, /positive/);
    assert.equal(
        chart.attributes['aria-label'],
        'One-day intraday price trend; color follows daily percentage change'
    );
    assert.equal(chart.children[0].tagName, 'polyline');
    assert.equal(chart.children[0].attributes.points.split(' ').length, 5);
});

test('charts show an unavailable state when there are too few valid prices', () => {
    const sparkline = MarketCharts.createSparkline([100], { domDocument: fakeDocument });
    const history = MarketCharts.createHistoryChart([{ close: 100 }], 'SPY', '1M', {
        domDocument: fakeDocument
    });

    assert.equal(sparkline.textContent, '—');
    assert.equal(history, null);
});

test('selected chart renders dated history as an accessible SVG', () => {
    const history = MarketCharts.createHistoryChart([
        { time: '2026-09-01', close: 100 },
        { time: '2026-09-02', close: 98 },
        { time: '2026-09-03', close: 102 }
    ], 'SPY', '5D', { domDocument: fakeDocument });

    assert.equal(history.tagName, 'svg');
    assert.equal(
        history.attributes['aria-label'],
        'SPY 5D closing-price history, +2.00% over selected range'
    );
    assert.equal(history.children[0].attributes.points.split(' ').length, 3);
});

test('selected 1D uses its own period change while the card follows daily change', () => {
    const sparkline = MarketCharts.createSparkline([105, 100], {
        dailyChange: 0.85,
        domDocument: fakeDocument
    });
    const selected = MarketCharts.createHistoryChart([
        { close: 105 },
        { close: 100 }
    ], 'SPY', '1D', {
        domDocument: fakeDocument
    });

    assert.match(sparkline.attributes.class, /positive/);
    assert.match(selected.attributes.class, /negative/);
    assert.equal(MarketCharts.calculatePeriodChange([{ close: 105 }, { close: 100 }]), -4.76);
});

test('negative daily percentage colors 1D lines red and missing change stays neutral', () => {
    const falling = MarketCharts.createSparkline([100, 105], {
        dailyChange: -0.5,
        domDocument: fakeDocument
    });
    const unavailable = MarketCharts.createSparkline([100, 105], {
        domDocument: fakeDocument
    });

    assert.match(falling.attributes.class, /negative/);
    assert.equal(unavailable.attributes.class, 'dropdown-chart');
});

test('longer selected ranges use their own first-to-last percentage', () => {
    const history = MarketCharts.createHistoryChart([
        { close: 105 },
        { close: 100 }
    ], 'SPY', '1M', {
        domDocument: fakeDocument
    });

    assert.match(history.attributes.class, /negative/);
    assert.match(history.attributes['aria-label'], /-4\.76% over selected range/);
});

test('a flat selected range stays neutral', () => {
    const history = MarketCharts.createHistoryChart([
        { close: 100 },
        { close: 100 }
    ], 'SPY', '1Y', { domDocument: fakeDocument });

    assert.equal(history.attributes.class, 'history-chart');
    assert.equal(MarketCharts.formatPeriodChange(0), '0.00%');
});

test('period change rejects missing or nonpositive prices', () => {
    assert.equal(MarketCharts.calculatePeriodChange([{ close: 100 }]), null);
    assert.equal(MarketCharts.calculatePeriodChange([{ close: 0 }, { close: 100 }]), null);
    assert.equal(MarketCharts.calculatePeriodChange([{ close: 100 }, { close: null }]), null);
});

test('one-day history labels show New York market times', () => {
    const label = MarketCharts.formatHistoryDate('2026-09-11T09:30:00-04:00', '1d');

    assert.match(label, /Sep 11/);
    assert.match(label, /9:30/);
    assert.match(label, /EDT/);
});
