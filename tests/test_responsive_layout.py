import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ResponsiveLayoutTests(unittest.TestCase):
    def test_every_page_includes_mobile_navigation_controls(self):
        template_names = (
            "index.html",
            "news.html",
            "economic_calendar.html",
            "coming_soon.html",
        )

        for template_name in template_names:
            page = (PROJECT_ROOT / "templates" / template_name).read_text(
                encoding="utf-8"
            )
            with self.subTest(template=template_name):
                self.assertIn("data-mobile-nav-toggle", page)
                self.assertIn('id="primary-navigation"', page)
                self.assertIn('/static/navigation.js', page)

    def test_responsive_styles_cover_supported_breakpoints(self):
        styles = (PROJECT_ROOT / "static" / "style.css").read_text(
            encoding="utf-8"
        )

        self.assertIn("@media (max-width: 1100px)", styles)
        self.assertIn("@media (max-width: 840px)", styles)
        self.assertIn("@media (max-width: 480px)", styles)
        self.assertIn("@media (max-width: 390px)", styles)
        self.assertIn("prefers-reduced-motion: reduce", styles)
        self.assertIn("overflow-x: hidden", styles)
        self.assertIn("flex-wrap: nowrap", styles)

    def test_calendar_has_mobile_labels_for_all_event_values(self):
        script = (
            PROJECT_ROOT / "static" / "economic-calendar-ui.js"
        ).read_text(encoding="utf-8")

        for label in ("Actual", "Forecast", "Previous"):
            self.assertIn(label, script)


if __name__ == "__main__":
    unittest.main()
