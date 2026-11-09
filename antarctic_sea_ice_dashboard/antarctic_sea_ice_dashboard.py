import reflex as rx
import antarctic_sea_ice_dashboard.models  # Register the schema without executing database operations.
from antarctic_sea_ice_dashboard.components.workspace import workspace
from antarctic_sea_ice_dashboard.states.uploaded_data import UploadedData
from antarctic_sea_ice_dashboard.states.antarctic_globe import AntarcticGlobe
from antarctic_sea_ice_dashboard.states.explorer import Explorer


def index() -> rx.Component:
    return workspace()


app = rx.App(
    head_components=[
        rx.el.link(rel="preconnect", href="https://fonts.googleapis.com"),
        rx.el.link(
            rel="preconnect",
            href="https://fonts.gstatic.com",
            cross_origin="",
        ),
        rx.el.link(
            href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap",
            rel="stylesheet",
        ),
        rx.el.link(
            href="https://unpkg.com/maplibre-gl@5.6.1/dist/maplibre-gl.css",
            rel="stylesheet",
        ),
        rx.el.script(
            src="https://unpkg.com/maplibre-gl@5.6.1/dist/maplibre-gl.js",
            defer=True,
        ),
        rx.el.script(
            src="https://unpkg.com/@deck.gl/core@9.1.14/dist.min.js",
            defer=True,
        ),
        rx.el.script(
            src="https://unpkg.com/@deck.gl/layers@9.1.14/dist.min.js",
            defer=True,
        ),
        rx.el.script(
            src="https://unpkg.com/@deck.gl/mapbox@9.1.14/dist.min.js",
            defer=True,
        ),
        rx.el.script(src="/antarctic_globe.js", defer=True),
    ],
)
app.add_page(
    index,
    route="/",
    title="Antarctic Sea Ice Explorer · Research Prototype",
    on_load=[
        Explorer.initialize,
        UploadedData.load_catalogue,
        AntarcticGlobe.refresh,
    ],
)
