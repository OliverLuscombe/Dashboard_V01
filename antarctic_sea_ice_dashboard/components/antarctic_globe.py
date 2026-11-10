import reflex as rx

from antarctic_sea_ice_dashboard.states.antarctic_globe import (
    AntarcticGlobe as Globe,
)
from antarctic_sea_ice_dashboard.states.uploaded_data import DatasetSummary


BUTTON = "inline-flex min-h-9 items-center justify-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-xs font-medium text-slate-600 hover:bg-slate-50 hover:text-sky-800 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-700 disabled:opacity-40 disabled:cursor-not-allowed"


def globe_layer(layer: DatasetSummary) -> rx.Component:
    return rx.el.label(
        rx.el.input(
            type="checkbox",
            checked=layer["active"],
            on_change=Globe.toggle_layer(layer["id"]),
            disabled=Globe.status == "loading",
            class_name="mt-0.5 h-4 w-4 accent-[#245f7e]",
        ),
        rx.el.span(
            rx.el.span(
                layer["name"],
                class_name="block break-words text-xs font-medium text-slate-800",
            ),
            rx.el.span(
                f"{layer['rows']:,} rows · {layer['filename']}",
                class_name="mt-1 block break-words text-[10px] text-slate-500",
            ),
            rx.cond(
                layer["map_message"] != "",
                rx.el.span(
                    layer["map_message"],
                    class_name="mt-1 block text-[10px] text-amber-700",
                ),
            ),
            class_name="min-w-0 flex-1",
        ),
        key=layer["id"],
        class_name="flex min-w-0 cursor-pointer items-start gap-2 rounded-md border border-slate-200 p-3 hover:bg-slate-50",
    )


def stat_card(label: str, value: rx.Var | str, detail: str) -> rx.Component:
    return rx.el.div(
        rx.el.p(label, class_name="text-[10px] font-medium text-slate-500"),
        rx.el.p(
            value,
            class_name="mt-1 break-words text-lg font-semibold text-[#183d54]",
        ),
        rx.el.p(detail, class_name="mt-1 text-[10px] text-slate-500"),
        class_name="min-w-0 rounded-lg border border-slate-200 bg-white p-3",
    )


def globe_map() -> rx.Component:
    return rx.el.section(
        rx.el.div(
            rx.el.div(
                rx.el.div(
                    rx.icon("globe", class_name="h-4 w-4 text-[#286180]"),
                    rx.el.h2(
                        "CSV observations · south-polar globe",
                        class_name="text-sm font-semibold text-slate-800",
                    ),
                    class_name="flex items-center gap-2",
                ),
                rx.el.p(
                    Globe.snapshot_label,
                    class_name="mt-1 text-xs font-medium text-[#245f7e]",
                ),
                rx.el.p(
                    Globe.source_name,
                    class_name="mt-1 break-words text-[10px] text-slate-500",
                ),
            ),
            rx.el.div(
                rx.el.label(
                    "Year and month",
                    html_for="globe-snapshot",
                    class_name="sr-only",
                ),
                rx.el.select(
                    rx.foreach(
                        Globe.groups,
                        lambda group: rx.el.option(
                            group["label"], value=group["key"]
                        ),
                    ),
                    id="globe-snapshot",
                    value=Globe.selected_group,
                    on_change=Globe.select_group,
                    disabled=(Globe.status == "loading")
                    | (Globe.groups.length() == 0),
                    class_name="min-h-9 max-w-48 rounded-md border border-slate-200 bg-white px-3 text-xs text-slate-700 focus-visible:outline-2 focus-visible:outline-sky-700 disabled:opacity-70",
                ),
                rx.el.label(
                    "Mapped measurement",
                    html_for="globe-measurement",
                    class_name="sr-only",
                ),
                rx.el.select(
                    rx.foreach(
                        Globe.measurements,
                        lambda measurement: rx.el.option(
                            measurement["label"],
                            value=measurement["key"],
                        ),
                    ),
                    id="globe-measurement",
                    value=Globe.measurement_key,
                    on_change=Globe.select_measurement,
                    disabled=(Globe.status == "loading")
                    | (Globe.measurements.length() == 0),
                    class_name="min-h-9 max-w-60 rounded-md border border-slate-200 bg-white px-3 text-xs text-slate-700 focus-visible:outline-2 focus-visible:outline-sky-700 disabled:opacity-70",
                ),
                rx.el.button(
                    rx.icon("refresh-cw", class_name="h-3.5 w-3.5"),
                    "Refresh",
                    on_click=Globe.refresh,
                    disabled=Globe.status == "loading",
                    class_name=BUTTON,
                ),
                class_name="flex flex-wrap items-center gap-2",
            ),
            class_name="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white p-4",
        ),
        rx.el.p(
            "Choose a Year/Month snapshot and enable one or more uploaded CSV layers from that group. Their valid observations are drawn together in one batched WebGL layer; missing or invalid values are omitted. Click a point to inspect its CSV, column, value, and coordinates. This is a geographic observation view, not an ice-thickness or terrain model.",
            class_name="border-b border-slate-200 bg-[#f4f8fa] px-4 py-3 text-[11px] leading-relaxed text-slate-600",
        ),
        rx.cond(
            Globe.status == "loading",
            rx.el.p(
                Globe.message,
                role="status",
                class_name="border-b border-slate-200 bg-white px-4 py-3 text-xs text-slate-600",
            ),
        ),
        rx.cond(
            Globe.status == "error",
            rx.el.p(
                Globe.message,
                role="alert",
                class_name="border-b border-red-200 bg-red-50 px-4 py-3 text-xs text-red-700",
            ),
        ),
        rx.el.div(
            rx.el.div(
                rx.el.h3(
                    "CSV layers in this snapshot",
                    class_name="text-xs font-semibold text-[#172e40]",
                ),
                rx.cond(
                    Globe.layers.length() > 0,
                    rx.el.div(
                        rx.foreach(Globe.layers, globe_layer),
                        class_name="mt-3 grid gap-2 sm:grid-cols-2",
                    ),
                    rx.el.p(
                        "No geographic CSV layers are configured for this date. Add one in Data.",
                        class_name="mt-2 text-xs text-slate-500",
                    ),
                ),
            ),
            class_name="border-b border-slate-200 bg-white p-4",
        ),
        rx.el.div(
            stat_card(
                "Valid mapped observations",
                rx.cond(Globe.status == "loading", "Loading…", Globe.valid),
                "Across enabled CSV layers",
            ),
            stat_card(
                "Mean selected measurement",
                rx.cond(Globe.average != "", Globe.average, "—"),
                Globe.measurement_label,
            ),
            stat_card(
                "Coordinate rows omitted",
                Globe.invalid_coordinates,
                "Missing, malformed, or out of range",
            ),
            stat_card(
                "Measurement rows omitted",
                Globe.invalid_readings,
                "Missing or invalid for selected field",
            ),
            class_name="grid grid-cols-2 gap-2 border-b border-slate-200 bg-[#f8fafb] p-3 lg:grid-cols-4",
        ),
        rx.el.div(
            rx.el.div(
                id="antarctic-globe-map",
                data_globe_source=rx.get_upload_url(Globe.filename),
                data_globe_snapshot=Globe.snapshot_label,
                data_globe_measurement=Globe.measurement_label,
                role="application",
                aria_label="Interactive south-polar globe showing uploaded CSV observations, coloured by the selected measurement. Click a point for its observation details.",
                class_name="h-[480px] w-full bg-[#dbe8ed] sm:h-[600px]",
            ),
            rx.el.div(
                rx.el.div(
                    rx.el.span(
                        rx.cond(
                            Globe.measurement_key == "sea_ice_concentration",
                            "0%",
                            "Low",
                        )
                    ),
                    rx.el.div(
                        class_name="h-3 flex-1 rounded-full bg-[linear-gradient(90deg,#17324d_0%,#2878a5_30%,#66b8a5_58%,#f2df77_78%,#d94b37_100%)]",
                    ),
                    rx.el.span(
                        rx.cond(
                            Globe.measurement_key == "sea_ice_concentration",
                            "100%",
                            "High",
                        )
                    ),
                    class_name="flex min-w-[240px] flex-1 items-center gap-3 text-[10px] font-medium text-slate-600",
                ),
                rx.el.span(
                    f"{Globe.measurement_label} · {Globe.value_range}",
                    class_name="text-[11px] font-medium text-slate-700",
                ),
                class_name="flex flex-wrap items-center gap-4 border-t border-slate-200 bg-white px-4 py-3",
            ),
            rx.el.div(
                rx.el.p(
                    f"{Globe.valid:,} rendered observations · {Globe.total:,} rows examined",
                    class_name="text-xs font-medium text-[#183d54]",
                ),
                rx.el.p(
                    f"Mapped CSV columns: {Globe.measurement_column} · {Globe.measurement_units} · one batched WebGL layer · refreshed {Globe.updated}",
                    class_name="mt-2 break-words text-[10px] text-slate-600",
                ),
                rx.el.p(
                    "Basemap © OpenStreetMap contributors · OpenFreeMap. The globe shows geography and observation locations only.",
                    class_name="mt-2 text-[10px] leading-relaxed text-slate-500",
                ),
                class_name="border-t border-slate-200 bg-white p-4",
            ),
            class_name="overflow-hidden rounded-b-lg border border-t-0 border-slate-200 bg-white",
        ),
        class_name="overflow-hidden rounded-lg border border-slate-200 bg-white",
    )
