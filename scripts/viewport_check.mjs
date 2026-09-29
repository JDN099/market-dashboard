import { mkdir, writeFile } from "node:fs/promises";
import process from "node:process";


const BASE_URL = process.argv[2] || "http://127.0.0.1:5000";
const DEBUG_URL = process.env.CHROME_DEBUG_URL || "http://127.0.0.1:9223";
const OUTPUT_DIRECTORY = new URL("../docs/screenshots/", import.meta.url);
const WIDTHS = [320, 375, 390, 768, 1024, 1440];
const ROUTES = [
    "/markets",
    "/watchlist-page",
    "/economic-calendar",
    "/earnings",
    "/sentiment",
    "/news-page",
];


class CdpConnection {
    constructor(webSocketUrl) {
        this.nextId = 1;
        this.pending = new Map();
        this.eventWaiters = new Map();
        this.socket = new WebSocket(webSocketUrl);
    }

    async open() {
        await new Promise((resolve, reject) => {
            this.socket.addEventListener("open", resolve, { once: true });
            this.socket.addEventListener("error", reject, { once: true });
        });

        this.socket.addEventListener("message", (event) => {
            const message = JSON.parse(event.data);
            if (message.id && this.pending.has(message.id)) {
                const pendingRequest = this.pending.get(message.id);
                this.pending.delete(message.id);
                if (message.error) {
                    pendingRequest.reject(new Error(message.error.message));
                } else {
                    pendingRequest.resolve(message.result);
                }
                return;
            }

            const waiters = this.eventWaiters.get(message.method) || [];
            this.eventWaiters.delete(message.method);
            waiters.forEach((resolve) => resolve(message.params));
        });
    }

    send(method, params = {}) {
        const id = this.nextId;
        this.nextId += 1;

        return new Promise((resolve, reject) => {
            this.pending.set(id, { reject, resolve });
            this.socket.send(JSON.stringify({ id, method, params }));
        });
    }

    waitForEvent(method, timeoutMs = 10000) {
        return new Promise((resolve, reject) => {
            const timeout = setTimeout(() => {
                reject(new Error(`Timed out waiting for ${method}`));
            }, timeoutMs);
            const waiters = this.eventWaiters.get(method) || [];
            waiters.push((params) => {
                clearTimeout(timeout);
                resolve(params);
            });
            this.eventWaiters.set(method, waiters);
        });
    }

    close() {
        this.socket.close();
    }
}


async function selectPageTarget() {
    const response = await fetch(`${DEBUG_URL}/json/list`);
    if (!response.ok) {
        throw new Error(`Chrome debugging endpoint returned ${response.status}`);
    }

    const targets = await response.json();
    const pageTarget = targets.find((target) => target.type === "page");
    if (!pageTarget) {
        throw new Error("Chrome did not expose a page target");
    }

    return pageTarget;
}


async function navigate(connection, url) {
    const loaded = connection.waitForEvent("Page.loadEventFired");
    await connection.send("Page.navigate", { url });
    await loaded;
}


async function evaluate(connection, expression) {
    const result = await connection.send("Runtime.evaluate", {
        expression,
        returnByValue: true,
    });

    if (result.exceptionDetails) {
        throw new Error(result.exceptionDetails.text || "Browser evaluation failed");
    }

    return result.result.value;
}


async function setViewport(connection, width, height = 900) {
    await connection.send("Emulation.setDeviceMetricsOverride", {
        deviceScaleFactor: 1,
        height,
        mobile: false,
        width,
    });
}


async function inspectPage(connection, width, route) {
    await setViewport(connection, width);
    await navigate(connection, `${BASE_URL}${route}`);

    return evaluate(
        connection,
        `(() => {
            const viewportWidth = window.innerWidth;
            const documentWidth = document.documentElement.scrollWidth;
            const bodyWidth = document.body.scrollWidth;
            const toggle = document.querySelector(".mobile-nav-toggle");
            const newsPanel = document.querySelector(".news-panel");
            return {
                bodyWidth,
                documentWidth,
                mobileToggleVisible: toggle && getComputedStyle(toggle).display !== "none",
                newsPanelVisible: newsPanel && getComputedStyle(newsPanel).display !== "none",
                overflow: Math.max(documentWidth, bodyWidth) > viewportWidth,
                undersizedPrimaryControls: Array.from(
                    document.querySelectorAll(
                        "button:not(.remove-card-btn), input:not([type='checkbox']), select"
                    )
                ).filter((element) => {
                    if (getComputedStyle(element).display === "none") {
                        return false;
                    }
                    const rectangle = element.getBoundingClientRect();
                    return rectangle.height > 0 && rectangle.height < 40;
                }).length,
                title: document.title,
                viewportWidth,
            };
        })()`
    );
}


async function verifyMobileNavigation(connection) {
    await setViewport(connection, 390);
    await navigate(connection, `${BASE_URL}/markets`);

    return evaluate(
        connection,
        `(() => {
            const toggle = document.querySelector("[data-mobile-nav-toggle]");
            const navigation = document.getElementById("primary-navigation");
            toggle.click();
            const links = Array.from(navigation.querySelectorAll("a"));
            const result = {
                expanded: toggle.getAttribute("aria-expanded") === "true",
                linkCount: links.length,
                linksMeetTouchTarget: links.every((link) => link.getBoundingClientRect().height >= 44),
                menuOpen: navigation.classList.contains("is-open"),
            };
            toggle.click();
            return result;
        })()`
    );
}


async function saveScreenshot(connection, width, filename) {
    await setViewport(connection, width);
    await navigate(connection, `${BASE_URL}/economic-calendar`);
    await new Promise((resolve) => {
        setTimeout(resolve, 2500);
    });
    const result = await connection.send("Page.captureScreenshot", {
        captureBeyondViewport: false,
        format: "png",
        fromSurface: true,
    });

    await mkdir(OUTPUT_DIRECTORY, { recursive: true });
    await writeFile(
        new URL(filename, OUTPUT_DIRECTORY),
        Buffer.from(result.data, "base64")
    );
}


async function main() {
    const target = await selectPageTarget();
    const connection = new CdpConnection(target.webSocketDebuggerUrl);
    await connection.open();
    await connection.send("Page.enable");
    await connection.send("Runtime.enable");

    const failures = [];
    const results = [];

    try {
        for (const width of WIDTHS) {
            for (const route of ROUTES) {
                const metrics = await inspectPage(connection, width, route);
                const expectedMobileNavigation = width <= 840;
                const passed = (
                    !metrics.overflow
                    && metrics.mobileToggleVisible === expectedMobileNavigation
                    && (width <= 1100 ? !metrics.newsPanelVisible : true)
                    && (width > 840 || metrics.undersizedPrimaryControls === 0)
                );
                const result = { passed, route, width, ...metrics };
                results.push(result);
                if (!passed) {
                    failures.push(result);
                }
            }
        }

        const navigationResult = await verifyMobileNavigation(connection);
        if (
            !navigationResult.expanded
            || !navigationResult.menuOpen
            || !navigationResult.linksMeetTouchTarget
            || navigationResult.linkCount !== 6
        ) {
            failures.push({
                route: "/markets mobile navigation",
                width: 390,
                ...navigationResult,
            });
        }

        await saveScreenshot(connection, 390, "marketv-mobile-390.png");
        await saveScreenshot(connection, 1440, "marketv-desktop.png");
    } finally {
        connection.close();
    }

    console.table(results.map((result) => ({
        body: result.bodyWidth,
        document: result.documentWidth,
        menu: result.mobileToggleVisible,
        overflow: result.overflow,
        page: result.route,
        passed: result.passed,
        smallControls: result.undersizedPrimaryControls,
        width: result.width,
    })));

    if (failures.length) {
        console.error(JSON.stringify(failures, null, 2));
        process.exitCode = 1;
    }
}


main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
});
