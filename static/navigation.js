(function (root, factory) {
    const api = factory();

    if (typeof module === "object" && module.exports) {
        module.exports = api;
    }

    root.MarketVNavigation = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
    function setOpen(toggle, navigation, isOpen) {
        toggle.setAttribute("aria-expanded", String(isOpen));
        navigation.classList.toggle("is-open", isOpen);
    }

    function init(documentObject, windowObject) {
        const documentRef = documentObject || document;
        const windowRef = windowObject || window;
        const toggle = documentRef.querySelector("[data-mobile-nav-toggle]");
        const navigation = documentRef.getElementById("primary-navigation");

        if (!toggle || !navigation) {
            return null;
        }

        setOpen(toggle, navigation, false);

        toggle.addEventListener("click", function () {
            const isOpen = toggle.getAttribute("aria-expanded") === "true";
            setOpen(toggle, navigation, !isOpen);
        });

        navigation.addEventListener("click", function (event) {
            if (event.target.closest("a")) {
                setOpen(toggle, navigation, false);
            }
        });

        documentRef.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
                setOpen(toggle, navigation, false);
                toggle.focus();
            }
        });

        if (typeof windowRef.matchMedia === "function") {
            const desktopQuery = windowRef.matchMedia("(min-width: 841px)");
            const handleDesktopChange = function (event) {
                if (event.matches) {
                    setOpen(toggle, navigation, false);
                }
            };

            if (typeof desktopQuery.addEventListener === "function") {
                desktopQuery.addEventListener("change", handleDesktopChange);
            }
        }

        return {
            navigation: navigation,
            toggle: toggle,
        };
    }

    if (typeof document !== "undefined") {
        document.addEventListener("DOMContentLoaded", function () {
            init(document, window);
        });
    }

    return {
        init: init,
        setOpen: setOpen,
    };
});
