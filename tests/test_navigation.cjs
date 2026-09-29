const assert = require("node:assert/strict");
const test = require("node:test");

const navigation = require("../static/navigation.js");


function createElement() {
    const attributes = new Map();
    const classes = new Set();

    return {
        classList: {
            contains(name) {
                return classes.has(name);
            },
            toggle(name, enabled) {
                if (enabled) {
                    classes.add(name);
                } else {
                    classes.delete(name);
                }
            },
        },
        getAttribute(name) {
            return attributes.get(name);
        },
        setAttribute(name, value) {
            attributes.set(name, value);
        },
    };
}


test("setOpen synchronizes the mobile menu and accessibility state", function () {
    const toggle = createElement();
    const menu = createElement();

    navigation.setOpen(toggle, menu, true);
    assert.equal(toggle.getAttribute("aria-expanded"), "true");
    assert.equal(menu.classList.contains("is-open"), true);

    navigation.setOpen(toggle, menu, false);
    assert.equal(toggle.getAttribute("aria-expanded"), "false");
    assert.equal(menu.classList.contains("is-open"), false);
});
