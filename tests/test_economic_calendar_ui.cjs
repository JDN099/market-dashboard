const assert = require('node:assert/strict');
const test = require('node:test');

const CalendarUi = require('../static/economic-calendar-ui.js');

class FakeElement {
    constructor(tagName) {
        this.tagName = tagName;
        this.children = [];
        this.textContent = '';
        this.className = '';
        this.attributes = {};
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

    setAttribute(name, value) {
        this.attributes[name] = value;
    }

    set innerHTML(_value) {
        throw new Error('Calendar data must not be parsed as HTML');
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

test('date navigation crosses month boundaries safely', () => {
    assert.equal(CalendarUi.shiftDate('2026-09-30', 1), '2026-10-01');
    assert.equal(CalendarUi.shiftDate('2026-09-01', -1), '2026-08-31');
});

test('event times can be formatted in a specified user timezone', () => {
    const value = CalendarUi.formatEventTime('2026-09-28T14:30:00Z', {
        locale: 'en-CA',
        timeZone: 'America/Toronto'
    });
    assert.match(value, /10:30/);
    assert.match(value, /EDT/);
});

test('events render required fields and preserve provider text as text', () => {
    const container = new FakeElement('section');
    CalendarUi.renderEvents(container, [{
        scheduled_at: '2026-09-28T14:30:00Z',
        name: '<img src=x onerror=alert(1)>',
        country: 'US',
        currency: 'USD',
        importance: 'high',
        reporting_period: 'August 2026',
        actual: '2.8%',
        forecast: '2.9%',
        previous: '3.0%',
        source: 'Bureau of Labor Statistics',
        source_url: 'https://www.bls.gov/news.release/cpi.nr0.htm'
    }], { locale: 'en-CA', timeZone: 'America/Toronto' }, fakeDocument);

    const nodes = descendants(container);
    assert.equal(nodes.some((node) => node.tagName === 'img'), false);
    assert.equal(nodes.some((node) => node.textContent === '<img src=x onerror=alert(1)>'), true);
    assert.equal(nodes.some((node) => node.textContent === 'US · USD'), true);
    assert.equal(nodes.some((node) => node.className === 'calendar-impact calendar-impact--high'), true);
    assert.equal(nodes.some((node) => node.textContent === '2.8%'), true);
    assert.equal(nodes.some((node) => node.textContent === 'August 2026'), true);
    const source = nodes.find((node) => node.className === 'calendar-source-link');
    assert.equal(source.href, 'https://www.bls.gov/news.release/cpi.nr0.htm');
    assert.equal(source.target, '_blank');
    assert.equal(source.rel, 'noopener noreferrer');
    assert.equal(container.attributes['aria-busy'], 'false');
});

test('loading, empty, stale and unavailable states are explicit', () => {
    const container = new FakeElement('section');
    for (const state of ['loading', 'empty', 'stale', 'unavailable']) {
        CalendarUi.renderState(container, `${state} message`, state, fakeDocument);
        assert.equal(container.children[0].className, `calendar-state calendar-state--${state}`);
        assert.equal(container.children[0].textContent, `${state} message`);
    }
});

test('impact filtering deduplicates display concerns from provider data', () => {
    const events = [
        { importance: 'high', name: 'CPI' },
        { importance: 'medium', name: 'JOLTS' },
        { importance: 'low', name: 'Other release' }
    ];

    assert.deepEqual(
        CalendarUi.filterEventsByImportance(events, ['high', 'low']).map((event) => event.name),
        ['CPI', 'Other release']
    );
    assert.deepEqual(CalendarUi.filterEventsByImportance(events, []), []);
});

test('local-date filtering keeps events on the visitor calendar day', () => {
    const events = [
        { scheduled_at: '2026-09-29T03:30:00Z', name: 'Late UTC release' },
        { scheduled_at: '2026-09-29T14:00:00Z', name: 'Daytime release' }
    ];
    const originalTimezone = process.env.TZ;
    process.env.TZ = 'America/Toronto';
    try {
        assert.deepEqual(
            CalendarUi.filterEventsByLocalDate(events, '2026-09-28').map((event) => event.name),
            ['Late UTC release']
        );
    } finally {
        process.env.TZ = originalTimezone;
    }
});

test('unsafe provider source URLs never become links', () => {
    assert.equal(CalendarUi.safeSourceUrl('javascript:alert(1)'), null);
    assert.equal(CalendarUi.safeSourceUrl('http://www.bls.gov/release'), null);
    assert.equal(CalendarUi.safeSourceUrl('https://user:pass@www.bls.gov/release'), null);

    const container = new FakeElement('section');
    CalendarUi.renderEvents(container, [{
        scheduled_at: '2026-09-28T14:30:00Z',
        name: 'CPI',
        country: 'US',
        currency: 'USD',
        importance: 'high',
        source: 'Unsafe source',
        source_url: 'javascript:alert(1)'
    }], {}, fakeDocument);

    assert.equal(descendants(container).some((node) => node.tagName === 'a'), false);
});
