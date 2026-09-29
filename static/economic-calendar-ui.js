const EconomicCalendarUi = (() => {
    const MONTH_FORMATTER = new Intl.DateTimeFormat(undefined, {
        weekday: 'long',
        month: 'long',
        day: 'numeric',
        year: 'numeric'
    });

    function localDateIso(value = new Date()) {
        const year = value.getFullYear();
        const month = String(value.getMonth() + 1).padStart(2, '0');
        const day = String(value.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }

    function shiftDate(dateValue, days) {
        const date = new Date(`${dateValue}T12:00:00Z`);
        date.setUTCDate(date.getUTCDate() + days);
        return date.toISOString().slice(0, 10);
    }

    function formatSelectedDate(dateValue) {
        return MONTH_FORMATTER.format(new Date(`${dateValue}T12:00:00`));
    }

    function formatEventTime(timestamp, options = {}) {
        const formatOptions = {
            hour: 'numeric',
            minute: '2-digit',
            timeZoneName: 'short'
        };
        if (options.timeZone) {
            formatOptions.timeZone = options.timeZone;
        }
        return new Intl.DateTimeFormat(options.locale, formatOptions).format(new Date(timestamp));
    }

    function formatLastUpdated(timestamp, options = {}) {
        if (!timestamp) {
            return 'Update time unavailable';
        }
        const formatOptions = {
            dateStyle: 'medium',
            timeStyle: 'short'
        };
        if (options.timeZone) {
            formatOptions.timeZone = options.timeZone;
        }
        return `Updated ${new Intl.DateTimeFormat(options.locale, formatOptions).format(new Date(timestamp))}`;
    }

    function safeSourceUrl(value) {
        if (typeof value !== 'string') {
            return null;
        }
        try {
            const url = new URL(value);
            if (url.protocol !== 'https:' || !url.hostname || url.username || url.password) {
                return null;
            }
            return url.href;
        } catch (error) {
            return null;
        }
    }

    function filterEventsByImportance(events, selectedImportances) {
        const allowed = new Set(selectedImportances);
        return events.filter((event) => allowed.has(event.importance));
    }

    function filterEventsByLocalDate(events, dateValue) {
        return events.filter((event) => {
            const scheduledAt = new Date(event.scheduled_at);
            return !Number.isNaN(scheduledAt.getTime()) && localDateIso(scheduledAt) === dateValue;
        });
    }

    function renderState(container, message, state, domDocument = document) {
        const element = domDocument.createElement('div');
        element.className = `calendar-state calendar-state--${state}`;
        element.textContent = String(message);
        container.replaceChildren(element);
        container.setAttribute('aria-busy', String(state === 'loading'));
    }

    function createMetric(labelText, value, domDocument) {
        const metric = domDocument.createElement('div');
        metric.className = 'calendar-event-metric';
        const label = domDocument.createElement('span');
        label.className = 'calendar-mobile-label';
        label.textContent = labelText;
        const content = domDocument.createElement('strong');
        content.textContent = value === null || value === undefined || value === '' ? '—' : String(value);
        metric.append(label, content);
        return metric;
    }

    function createEvent(event, options, domDocument) {
        const item = domDocument.createElement('article');
        item.className = 'calendar-event';

        const time = domDocument.createElement('time');
        time.dateTime = String(event.scheduled_at || '');
        time.textContent = formatEventTime(event.scheduled_at, options);

        const identity = domDocument.createElement('div');
        identity.className = 'calendar-event-identity';
        const name = domDocument.createElement('h3');
        name.textContent = String(event.name || 'Untitled event');
        const market = domDocument.createElement('span');
        market.className = 'calendar-event-market';
        market.textContent = [event.country, event.currency].filter(Boolean).join(' · ');
        identity.append(name, market);
        if (event.reporting_period) {
            const period = domDocument.createElement('span');
            period.className = 'calendar-reporting-period';
            period.textContent = String(event.reporting_period);
            identity.appendChild(period);
        }
        const sourceUrl = safeSourceUrl(event.source_url);
        if (sourceUrl) {
            const source = domDocument.createElement('a');
            source.className = 'calendar-source-link';
            source.href = sourceUrl;
            source.target = '_blank';
            source.rel = 'noopener noreferrer';
            source.textContent = String(event.source || 'Official source');
            identity.appendChild(source);
        }

        const impact = domDocument.createElement('span');
        const importance = ['low', 'medium', 'high'].includes(event.importance)
            ? event.importance
            : 'low';
        impact.className = `calendar-impact calendar-impact--${importance}`;
        impact.textContent = importance;

        item.append(
            time,
            identity,
            impact,
            createMetric('Actual', event.actual, domDocument),
            createMetric('Forecast', event.forecast, domDocument),
            createMetric('Previous', event.previous, domDocument)
        );
        return item;
    }

    function renderEvents(container, events, options = {}, domDocument = document) {
        const elements = events.map((event) => {
            return createEvent(event, options, domDocument);
        });
        container.replaceChildren(...elements);
        container.setAttribute('aria-busy', 'false');
    }

    return {
        localDateIso,
        shiftDate,
        formatSelectedDate,
        formatEventTime,
        formatLastUpdated,
        safeSourceUrl,
        filterEventsByImportance,
        filterEventsByLocalDate,
        renderState,
        renderEvents
    };
})();

if (typeof module !== 'undefined' && module.exports) {
    module.exports = EconomicCalendarUi;
}
