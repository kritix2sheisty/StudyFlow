import os

import reflex as rx

# Reflex's dev reloader watches every top-level entry of the project.
# The database lives in data/, and a write there must not restart the
# backend: each restart drops connections and in-memory state, which
# showed up as connection resets and rolled-back state during testing.
# Hidden directories (.states, .logs, .web) are excluded by Reflex
# itself. This is read before the reloader starts, so it takes effect
# for `reflex run`; an explicit environment variable still wins.
os.environ.setdefault("REFLEX_HOT_RELOAD_EXCLUDE_PATHS", "data")

config = rx.Config(
    app_name="StudyFlow",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
        rx.plugins.RadixThemesPlugin(),
    ]
)
