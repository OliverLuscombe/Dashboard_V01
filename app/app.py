import reflex as rx
import app.models  # Register the schema without executing database operations.
from app.components.workspace import workspace
from app.states.uploaded_data import UploadedData


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
    ],
)
app.add_page(
    index,
    route="/",
    title="Antarctic Sea Ice Explorer · Research Prototype",
    on_load=UploadedData.load_catalogue,
)
