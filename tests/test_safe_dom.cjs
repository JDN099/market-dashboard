const assert = require('node:assert/strict');
const test = require('node:test');

const MarketDom = require('../static/safe-dom.js');

class FakeElement {
    constructor(tagName) {
        this.tagName = tagName;
        this.children = [];
        this.textContent = '';
        this.className = '';
    }

    append(...children) {
        this.children.push(...children);
    }

    appendChild(child) {
        this.children.push(child);
    }

    replaceChildren(...children) {
        this.children = [...children];
    }

    set innerHTML(_value) {
        throw new Error('External data must not be parsed as HTML');
    }
}

const fakeDocument = {
    createElement(tagName) {
        return new FakeElement(tagName);
    }
};

function descendants(element) {
    return [element, ...element.children.flatMap(descendants)];
}

test('only absolute HTTP(S) article links are allowed', () => {
    assert.equal(MarketDom.safeArticleUrl('https://example.com/story'), 'https://example.com/story');
    assert.equal(MarketDom.safeArticleUrl('http://example.com/story'), 'http://example.com/story');
    assert.equal(MarketDom.safeArticleUrl('javascript:alert(1)'), null);
    assert.equal(MarketDom.safeArticleUrl('data:text/html,<script>alert(1)</script>'), null);
    assert.equal(MarketDom.safeArticleUrl('/relative-story'), null);
    assert.equal(MarketDom.safeArticleUrl('https://user:pass@example.com/story'), null);
});

test('hostile news fields remain text and unsupported links are not clickable', () => {
    const headline = '<img src=x onerror=alert(1)>';
    const article = MarketDom.createNewsArticle({
        title: headline,
        source: '<script>alert(1)</script>',
        symbols: ['<svg onload=alert(1)>'],
        importance: 'critical extra-class',
        url: 'javascript:alert(1)',
        published_at: '2026-01-01'
    }, () => '1h ago', fakeDocument);

    const nodes = descendants(article);
    assert.equal(article.className, 'news-item news-item--normal');
    assert.equal(nodes.some((node) => node.tagName === 'a'), false);
    assert.equal(nodes.some((node) => node.tagName === 'img'), false);
    assert.equal(nodes.find((node) => node.tagName === 'p').textContent, headline);
    assert.equal(nodes.find((node) => node.className === 'news-tag').textContent, '<svg onload=alert(1)>');
});

test('safe news links preserve the existing new-tab protections', () => {
    const article = MarketDom.createNewsArticle({
        title: 'Market update',
        source: 'Example',
        symbols: [],
        importance: 'critical',
        url: 'https://example.com/story'
    }, () => 'Just now', fakeDocument);

    const link = descendants(article).find((node) => node.tagName === 'a');
    assert.equal(link.href, 'https://example.com/story');
    assert.equal(link.target, '_blank');
    assert.equal(link.rel, 'noopener noreferrer');
    assert.equal(link.textContent, 'Market update');
    assert.equal(descendants(article).find((node) => node.className.includes('news-priority')).textContent, 'Important');
});

test('error messages and quote names remain plain text', () => {
    const container = new FakeElement('section');
    MarketDom.renderNewsState(container, '<script>alert(1)</script>', fakeDocument);
    assert.equal(container.children[0].textContent, '<script>alert(1)</script>');

    MarketDom.renderQuoteDetail(container, {
        symbol: 'AAPL',
        name: '<img src=x onerror=alert(1)>',
        price: 100,
        change: null,
        day_low: 99,
        day_high: 101,
        volume: 1000,
        size_label: '<script>fake</script>',
        size_value: 1000000
    }, {
        formatMetric(value, formatter) {
            return formatter(value);
        },
        formatPrice(value) {
            return value.toFixed(2);
        },
        formatCompactNumber(value) {
            return String(value);
        },
        formatCompactCurrency(value) {
            return String(value);
        }
    }, fakeDocument);

    const nodes = descendants(container);
    assert.equal(nodes.some((node) => node.tagName === 'img'), false);
    assert.equal(nodes.find((node) => node.tagName === 'p').textContent, '<img src=x onerror=alert(1)>');
    assert.equal(nodes.some((node) => node.textContent === '<script>fake</script>'), true);
    assert.equal(nodes.some((node) => node.textContent === 'Change unavailable'), true);
});
