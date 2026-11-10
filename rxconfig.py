import os
from pathlib import Path

import reflex as rx
import reflex_xy

database_path = Path(__file__).resolve().with_name("globe_check.db")
database_url = os.getenv(
    "REFLEX_DB_URL",
    f"sqlite:///{database_path.as_posix()}",
)

config = rx.Config(
    app_name="antarctic_sea_ice_dashboard",
    db_url=database_url,
    default_color_mode="light",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
        reflex_xy.XYPlugin(),
    ],
)
