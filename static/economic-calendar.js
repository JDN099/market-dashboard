document.addEventListener('DOMContentLoaded', function () {
    const dateInput = document.getElementById('calendar-date');
    const countryInput = document.getElementById('calendar-country');
    const importanceInputs = Array.from(
        document.querySelectorAll('#calendar-importance input[type="checkbox"]')
    );
    const selectedDate = document.getElementById('calendar-selected-date');
    const timezoneLabel = document.getElementById('calendar-timezone');
    const status = document.getElementById('calendar-data-status');
    const lastUpdated = document.getElementById('calendar-last-updated');
    const staleWarning = document.getElementById('calendar-stale-warning');
    const eventList = document.getElementById('economic-calendar-list');
    let requestId = 0;

    function updateDateContext() {
        selectedDate.textContent = EconomicCalendarUi.formatSelectedDate(dateInput.value);
    }

    async function loadEvents() {
        const currentRequestId = ++requestId;
        updateDateContext();
        status.textContent = 'Loading data';
        staleWarning.hidden = true;
        EconomicCalendarUi.renderState(eventList, 'Loading economic events…', 'loading');
        const selectedImportances = importanceInputs.filter((input) => {
            return input.checked;
        }).map((input) => {
            return input.value;
        });
        if (selectedImportances.length === 0) {
            status.textContent = 'No impacts selected';
            EconomicCalendarUi.renderState(
                eventList,
                'Select at least one impact level to view economic events.',
                'empty'
            );
            return;
        }
        const parameters = new URLSearchParams({
            start: EconomicCalendarUi.shiftDate(dateInput.value, -1),
            end: EconomicCalendarUi.shiftDate(dateInput.value, 1),
            country: countryInput.value,
            importance: selectedImportances.join(',')
        });

        try {
            const response = await fetch(`/api/economic-calendar?${parameters}`);
            const data = await response.json();
            if (currentRequestId !== requestId) {
                return;
            }
            if (!response.ok) {
                throw new Error(data.error || 'Economic calendar data is unavailable right now.');
            }
            const events = Array.isArray(data.events)
                ? EconomicCalendarUi.filterEventsByLocalDate(data.events, dateInput.value)
                : [];
            if (events.length === 0) {
                EconomicCalendarUi.renderState(
                    eventList,
                    'No economic events match these filters for this date.',
                    'empty'
                );
            } else {
                EconomicCalendarUi.renderEvents(eventList, events);
            }
            const meta = data.meta || {};
            status.textContent = meta.stale ? 'Stale data' : 'Official source';
            lastUpdated.textContent = EconomicCalendarUi.formatLastUpdated(meta.last_updated);
            if (meta.stale) {
                staleWarning.textContent = meta.warning || 'Showing stored events because the official source is temporarily unavailable.';
                staleWarning.hidden = false;
            }
        } catch (error) {
            if (currentRequestId !== requestId) {
                return;
            }
            EconomicCalendarUi.renderState(eventList, error.message, 'unavailable');
            status.textContent = 'Unavailable';
            lastUpdated.textContent = 'Update unavailable';
        }
    }

    function selectDate(dateValue) {
        dateInput.value = dateValue;
        loadEvents();
    }

    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    timezoneLabel.textContent = timezone
        ? `Times shown in ${timezone}`
        : 'Times shown in your local timezone';
    dateInput.value = EconomicCalendarUi.localDateIso();

    document.getElementById('calendar-previous').addEventListener('click', () => {
        selectDate(EconomicCalendarUi.shiftDate(dateInput.value, -1));
    });
    document.getElementById('calendar-today').addEventListener('click', () => {
        selectDate(EconomicCalendarUi.localDateIso());
    });
    document.getElementById('calendar-next').addEventListener('click', () => {
        selectDate(EconomicCalendarUi.shiftDate(dateInput.value, 1));
    });
    dateInput.addEventListener('change', loadEvents);
    countryInput.addEventListener('change', loadEvents);
    for (const input of importanceInputs) {
        input.addEventListener('change', loadEvents);
    }

    DashboardShell.init();
    loadEvents();
});
