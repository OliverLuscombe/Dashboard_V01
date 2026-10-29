import reflex as rx
from app.states.overview_grid import OverviewGrid as G, GridLayer, GridLegend


BUTTON = "inline-flex min-h-9 items-center justify-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-xs font-medium text-slate-600 hover:bg-slate-50 hover:text-sky-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-700 disabled:opacity-40 disabled:cursor-not-allowed"


def grid_layer(layer: GridLayer) -> rx.Component:
    return rx.el.button(
        rx.icon(
            rx.cond(G.selected_layer == layer["key"], "circle-check", "circle"),
            class_name="h-4 w-4 shrink-0",
        ),
        rx.el.div(
            rx.el.span(
                layer["label"], class_name="block text-left text-xs font-medium"
            ),
            rx.el.span(
                layer["column"],
                class_name="mt-1 block break-words text-left text-[10px] text-slate-600",
            ),
            class_name="min-w-0",
        ),
        on_click=G.choose_layer(layer["key"]),
        aria_pressed=G.selected_layer == layer["key"],
        disabled=G.status == "loading",
        key=layer["key"],
        class_name=rx.cond(
            G.selected_layer == layer["key"],
            "flex w-full items-center gap-2 rounded-md border border-sky-200 bg-[#edf5f8] px-3 py-2.5 text-[#245f7e] focus-visible:outline-2 focus-visible:outline-sky-700 disabled:opacity-50",
            "flex w-full items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-2.5 text-slate-700 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-sky-700 disabled:opacity-50",
        ),
    )


def category_legend(entry: GridLegend) -> rx.Component:
    return rx.el.li(
        rx.el.img(
            src=entry["swatch"],
            alt="",
            class_name="h-3 w-3 shrink-0 rounded-xs [image-rendering:pixelated]",
        ),
        rx.el.span(entry["label"], class_name="break-words"),
        key=entry["label"],
        class_name="flex items-center gap-2 text-[11px] text-slate-700",
    )


def grid_legend() -> rx.Component:
    return rx.el.div(
        rx.el.h3(G.label, class_name="text-xs font-semibold text-[#183d54]"),
        rx.cond(
            G.discrete,
            rx.el.div(
                rx.el.p(
                    "Discrete CSV labels · no inferred ice zone or trained clusters",
                    class_name="mt-1 text-[11px] text-slate-600",
                ),
                rx.el.ul(
                    rx.foreach(G.legends, category_legend),
                    class_name="mt-3 flex flex-wrap gap-x-5 gap-y-2",
                ),
            ),
            rx.el.div(
                rx.el.img(
                    src=rx.get_upload_url(G.legend_filename),
                    alt="Continuous colour ramp from pale cyan for the lowest reading to navy for the highest reading",
                    class_name="mt-3 h-3 w-full rounded-xs [image-rendering:pixelated]",
                ),
                rx.el.div(
                    rx.el.span(G.minimum),
                    rx.cond(
                        G.minimum == G.maximum,
                        rx.el.span("Constant value · midpoint colour"),
                        rx.el.span("Observed minimum → maximum"),
                    ),
                    rx.el.span(G.maximum),
                    class_name="mt-1 flex flex-wrap justify-between gap-2 text-[10px] text-slate-600",
                ),
                rx.el.p(
                    "Range across rendered pixels, not a scientific threshold. Units follow your mapping and have not been verified.",
                    class_name="mt-2 text-[11px] text-slate-600",
                ),
            ),
        ),
        rx.el.p(
            "Transparent pixels have no rendered reading; the grey background is not a measured value.",
            class_name="mt-3 text-[11px] text-slate-600",
        ),
        class_name="border-t border-slate-200 bg-white p-4",
    )


def grid_map() -> rx.Component:
    return rx.el.section(
        rx.el.div(
            rx.el.div(
                rx.el.div(
                    rx.icon("grid-2x2", class_name="h-4 w-4 text-[#286180]"),
                    rx.el.h2(
                        "Uploaded CSV · pixel grid",
                        class_name="text-sm font-semibold text-slate-800",
                    ),
                    class_name="flex items-center gap-2",
                ),
                rx.el.p(
                    G.source_name,
                    class_name="mt-1 break-words text-xs text-[#245f7e]",
                ),
            ),
            rx.el.button(
                rx.icon("refresh-cw", class_name="h-3.5 w-3.5"),
                "Refresh map",
                on_click=G.refresh,
                disabled=G.status == "loading",
                class_name=BUTTON,
            ),
            class_name="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white p-4",
        ),
        rx.el.p(
            "316 columns × 332 rows · x increases left → right; y decreases top → bottom. Pixel coordinates, NOT a latitude/longitude projection.",
            class_name="border-b border-slate-200 bg-[#f4f8fa] px-4 py-3 text-[11px] leading-relaxed text-slate-600",
        ),
        rx.match(
            G.status,
            (
                "loading",
                rx.el.div(
                    rx.icon(
                        "loader-circle",
                        class_name="h-6 w-6 animate-spin text-[#286180]",
                    ),
                    rx.el.p(G.message, class_name="text-xs text-slate-600"),
                    role="status",
                    class_name="flex min-h-[420px] flex-col items-center justify-center gap-4 bg-[#f4f8fa] p-6",
                ),
            ),
            (
                "ready",
                rx.el.figure(
                    rx.el.div(
                        rx.el.span("x = 1"),
                        rx.el.span("x = 316"),
                        class_name="flex justify-between text-[10px] text-slate-600",
                    ),
                    rx.el.div(
                        rx.el.div(
                            rx.el.span("y = 332"),
                            rx.el.span("y = 1"),
                            class_name="flex w-12 shrink-0 flex-col justify-between py-1 text-[10px] text-slate-600",
                        ),
                        rx.el.img(
                            src=rx.get_upload_url(G.filename),
                            alt=f"Uploaded {G.label} at actual CSV pixel positions. 316 columns by 332 rows; top-left (1,332), bottom-right (316,1). Transparent cells are missing readings.",
                            width=316,
                            height=332,
                            class_name="block h-auto w-full min-w-0 border border-slate-300 bg-slate-100 [image-rendering:pixelated]",
                        ),
                        class_name="mt-2 flex items-stretch",
                    ),
                    rx.el.figcaption(
                        f"Source column: {G.column} · no interpolation or synthetic landmass",
                        class_name="mt-3 break-words text-[11px] text-slate-600",
                    ),
                    class_name="mx-auto w-full max-w-[480px] bg-[#f4f8fa] p-5",
                ),
            ),
            rx.el.div(
                rx.icon(
                    rx.cond(G.status == "error", "circle-alert", "scan-line"),
                    class_name="h-7 w-7 text-[#286180]",
                ),
                rx.el.h3(
                    rx.cond(
                        G.status == "unmapped",
                        "Measurement not mapped",
                        rx.cond(
                            G.status == "empty",
                            "No valid readings",
                            "Source / renderer error",
                        ),
                    ),
                    class_name="text-sm font-semibold text-[#183d54]",
                ),
                rx.el.p(
                    G.message,
                    class_name="max-w-lg text-center text-xs leading-relaxed text-slate-600",
                ),
                role="status",
                class_name="flex min-h-[360px] flex-col items-center justify-center gap-3 bg-[#f4f8fa] p-6",
            ),
        ),
        rx.cond(G.status == "ready", grid_legend()),
        rx.cond(
            (G.status == "ready") | (G.status == "empty"),
            rx.el.div(
                rx.el.p(
                    f"{G.valid:,} valid rendered pixels · {G.skipped:,} skipped rows · {G.total:,} rows examined",
                    class_name="text-xs font-medium text-[#183d54]",
                ),
                rx.el.p(
                    f"Skipped: {G.invalid_coordinates:,} invalid coordinates / malformed rows; {G.duplicates:,} duplicate coordinates; {G.invalid_readings:,} empty or invalid readings.",
                    class_name="mt-2 text-[11px] leading-relaxed text-slate-600",
                ),
                rx.el.p(
                    f"{104912 - G.valid:,} pixels transparent. First saved row at each coordinate wins (row position, then row ID), even if its measurement is empty; later duplicates are skipped.",
                    class_name="mt-2 text-[11px] leading-relaxed text-slate-600",
                ),
                rx.el.p(
                    f"Rendered snapshot · {G.updated}",
                    class_name="mt-2 text-[10px] text-slate-600",
                ),
                class_name="border-t border-slate-200 bg-white p-4",
            ),
        ),
        class_name="min-w-0 overflow-hidden rounded-lg border border-slate-200 bg-[#f4f8fa]",
    )


def grid_inspector() -> rx.Component:
    return rx.el.section(
        rx.el.h3(
            "Pixel inspector", class_name="text-sm font-semibold text-slate-800"
        ),
        rx.el.p(
            "Inspect a saved row by its actual pixel x/y, not a region or geographic location.",
            class_name="mt-2 text-[11px] leading-relaxed text-slate-600",
        ),
        rx.el.form(
            rx.el.div(
                rx.el.div(
                    rx.el.label(
                        "x · 1–316",
                        html_for="inspect-pixel-x",
                        class_name="mb-1 block text-[11px] font-medium text-slate-600",
                    ),
                    rx.el.input(
                        id="inspect-pixel-x",
                        name="x",
                        type="number",
                        min=1,
                        max=316,
                        step=1,
                        required=True,
                        default_value="1",
                        class_name="min-h-9 w-full rounded-md border border-slate-300 bg-white px-2 text-xs text-slate-800 focus-visible:outline-2 focus-visible:outline-sky-700",
                    ),
                ),
                rx.el.div(
                    rx.el.label(
                        "y · 1–332",
                        html_for="inspect-pixel-y",
                        class_name="mb-1 block text-[11px] font-medium text-slate-600",
                    ),
                    rx.el.input(
                        id="inspect-pixel-y",
                        name="y",
                        type="number",
                        min=1,
                        max=332,
                        step=1,
                        required=True,
                        default_value="332",
                        class_name="min-h-9 w-full rounded-md border border-slate-300 bg-white px-2 text-xs text-slate-800 focus-visible:outline-2 focus-visible:outline-sky-700",
                    ),
                ),
                class_name="grid grid-cols-2 gap-3",
            ),
            rx.el.button(
                rx.cond(G.inspecting, "Looking up…", "Inspect pixel"),
                type="submit",
                disabled=G.inspecting
                | (G.status == "loading")
                | (G.source_id == 0),
                class_name="mt-3 min-h-9 w-full rounded-md bg-[#245f7e] px-3 text-xs font-medium text-white hover:bg-sky-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-700 disabled:cursor-not-allowed disabled:opacity-50",
            ),
            on_submit=G.inspect_pixel,
            class_name="mt-4",
        ),
        rx.el.p(
            G.inspection,
            role="status",
            class_name="mt-4 break-words text-xs font-medium leading-relaxed text-[#245f7e]",
        ),
        rx.el.dl(
            rx.foreach(
                G.inspection_details,
                lambda detail: rx.el.div(
                    rx.el.dt(
                        detail["label"],
                        class_name="text-[10px] leading-relaxed text-slate-600",
                    ),
                    rx.el.dd(
                        detail["value"],
                        class_name="mt-1 break-words text-xs font-semibold text-slate-800",
                    ),
                    class_name="border-t border-slate-100 py-2.5",
                ),
            ),
            class_name="mt-3",
        ),
        rx.el.p(
            "Lookup reads current saved data. Refresh the map after edits to update the rendered snapshot. Duplicate selection follows the same first-row rule.",
            class_name="mt-3 text-[10px] leading-relaxed text-slate-600",
        ),
        class_name="border-t border-slate-200 p-4",
    )


def uploaded_overview() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.icon("info", class_name="h-4 w-4 shrink-0 text-[#286180]"),
            rx.el.div(
                rx.el.p(
                    "Uploaded map only · Overview summaries unavailable",
                    class_name="text-xs font-semibold text-[#183d54]",
                ),
                rx.el.p(
                    "Extent, seasonal chart and model summary are hidden: they are not calculated from this CSV. The existing year/month controls belong to the demo and do not filter this grid. All saved rows are considered; duplicate coordinates are not interpreted as a time series.",
                    class_name="mt-1 text-[11px] leading-relaxed text-slate-600",
                ),
            ),
            class_name="mb-4 flex gap-3 rounded-lg border border-slate-200 bg-[#edf4f7] p-4",
        ),
        rx.el.div(
            grid_map(),
            rx.el.aside(
                rx.el.div(
                    rx.el.h3(
                        "Available measurements",
                        class_name="text-sm font-semibold text-slate-800",
                    ),
                    rx.el.p(
                        "Select one mapped variable at a time. Unmapped measurements are not offered or derived.",
                        class_name="mt-2 text-[11px] leading-relaxed text-slate-600",
                    ),
                    rx.el.div(
                        rx.foreach(G.layers, grid_layer),
                        class_name="mt-3 flex flex-col gap-2",
                    ),
                    rx.cond(
                        G.layers.length() == 0,
                        rx.el.p(
                            "No mapped measurements loaded.",
                            class_name="mt-3 text-xs text-slate-600",
                        ),
                    ),
                    rx.el.p(
                        "Numeric layers require finite values. Categorical layers accept up to 32 distinct CSV labels; empty/NA/non-finite labels or labels over 120 characters are missing. No scientific quality or unit validation is implied.",
                        class_name="mt-3 text-[10px] leading-relaxed text-slate-600",
                    ),
                    class_name="p-4",
                ),
                grid_inspector(),
                class_name="min-w-0 self-start rounded-lg border border-slate-200 bg-white",
            ),
            class_name="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_300px]",
        ),
        class_name="w-full min-w-0",
    )
