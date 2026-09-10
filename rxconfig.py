import reflex as rx

config = rx.Config(
    app_name="studyflow_web",
    # The page uses Radix components; say so explicitly (Reflex 0.9 warns otherwise).
    plugins=[rx.plugins.RadixThemesPlugin()],
    # No sitemap needed for a single-page app.
    disable_plugins=[rx.plugins.SitemapPlugin],
)
