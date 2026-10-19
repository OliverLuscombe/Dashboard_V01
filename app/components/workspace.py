import reflex as rx
import reflex_xy as xy
from app.states.explorer import Explorer as S
from app.components.uploaded_data import uploaded_workspace


BUTTON = "inline-flex min-h-9 items-center justify-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-xs font-medium text-slate-600 hover:bg-slate-50 hover:text-sky-800 transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-700"
PANEL = "rounded-lg border border-slate-200 bg-white"


def action(label: str, icon: str, event: rx.event.EventType) -> rx.Component:
    return rx.el.button(
        rx.icon(icon, class_name="h-4 w-4"),
        label,
        on_click=event,
        class_name=BUTTON,
    )


def selector(
    label: str,
    value: rx.Var,
    options: list[str] | rx.Var,
    event: rx.event.EventType,
) -> rx.Component:
    return rx.el.label(
        rx.el.span(label, class_name="sr-only"),
        rx.el.select(
            rx.foreach(
                options, lambda option: rx.el.option(option, value=option)
            ),
            value=value,
            on_change=event,
            class_name="appearance-none w-full min-h-9 rounded-md border border-slate-200 bg-white py-2 pl-3 pr-9 text-xs font-medium text-slate-700 focus-visible:outline-2 focus-visible:outline-sky-700",
        ),
        rx.icon(
            "chevron-down",
            class_name="pointer-events-none absolute right-3 top-3 h-3 w-3 text-slate-500",
        ),
        class_name="relative block",
    )


def nav_item(label: str, icon: str) -> rx.Component:
    return rx.el.button(
        rx.icon(icon, class_name="h-[18px] w-[18px] shrink-0"),
        rx.el.span(label, class_name="hidden lg:block"),
        rx.cond(
            S.page == label,
            rx.el.span(
                class_name="ml-auto hidden lg:block h-1.5 w-1.5 rounded-full bg-sky-700"
            ),
        ),
        title=label,
        on_click=S.navigate(label),
        class_name=rx.cond(
            S.page == label,
            "flex items-center gap-3 w-full min-h-11 rounded-md px-3 text-sm font-medium bg-[#e7eff4] text-[#185375] focus-visible:outline-2 focus-visible:outline-sky-700",
            "flex items-center gap-3 w-full min-h-11 rounded-md px-3 text-sm text-slate-600 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-sky-700",
        ),
    )


def sidebar() -> rx.Component:
    return rx.el.aside(
        rx.el.div(
            rx.el.div(
                rx.icon("orbit", class_name="h-7 w-7 text-[#246383]"),
                class_name="rounded-lg bg-[#e6eff4] p-2",
            ),
            rx.el.div(
                rx.el.p(
                    "ANTARCTIC",
                    class_name="text-xs tracking-[0.16em] font-semibold text-slate-800",
                ),
                rx.el.p(
                    "SEA ICE EXPLORER",
                    class_name="mt-1 text-[9px] tracking-[0.13em] text-slate-500",
                ),
                class_name="hidden lg:block",
            ),
            class_name="flex items-center gap-2.5 h-[78px] shrink-0 px-4 lg:px-5",
        ),
        rx.el.nav(
            rx.el.p(
                "RESEARCH WORKSPACE",
                class_name="hidden lg:block mb-4 mt-6 px-3 text-[10px] tracking-[0.12em] text-slate-500",
            ),
            nav_item("Overview", "layout-dashboard"),
            nav_item("Map Explorer", "globe"),
            nav_item("Compare", "columns-2"),
            nav_item("Model Insights", "network"),
            rx.el.div(class_name="my-4 border-t border-slate-200"),
            nav_item("Data", "database"),
            nav_item("About", "info"),
            class_name="flex flex-1 min-h-0 flex-col gap-1 overflow-y-auto px-3",
        ),
        rx.el.div(
            rx.el.div(
                rx.icon("flask-conical", class_name="h-4 w-4 text-teal-700"),
                rx.el.span(
                    "Demo environment",
                    class_name="hidden lg:block text-xs font-medium text-slate-700",
                ),
                class_name="flex items-center gap-2",
            ),
            rx.el.p(
                "Synthetic science · shared CSVs",
                class_name="hidden lg:block mt-2 text-[11px] text-slate-500",
            ),
            rx.el.div(
                "RESEARCH PROTOTYPE  /  v0.1",
                class_name="hidden lg:block mt-5 text-[9px] tracking-wider text-slate-500",
            ),
            class_name="border-t border-slate-200 p-5",
        ),
        class_name="flex h-full w-[72px] lg:w-[208px] shrink-0 flex-col border-r border-slate-200 bg-[#f8fafb]",
    )


def header() -> rx.Component:
    return rx.el.header(
        rx.el.div(
            rx.el.p(
                "Antarctic Sea Ice Explorer",
                class_name="text-sm font-semibold text-slate-800",
            ),
            rx.el.p(
                "Environmental & machine learning analysis",
                class_name="mt-0.5 text-[11px] text-slate-500",
            ),
        ),
        rx.el.div(
            rx.el.span(
                rx.el.span(class_name="h-1.5 w-1.5 rounded-full bg-teal-600"),
                "Synthetic dataset",
                class_name="hidden sm:flex items-center gap-2 text-xs text-slate-600",
            ),
            rx.el.div(class_name="h-6 border-l border-slate-200"),
            action("Display", "sliders-horizontal", S.show_display),
            action("Help", "circle-help", S.navigate("About")),
            class_name="flex items-center gap-4",
        ),
        class_name="flex h-[68px] shrink-0 items-center justify-between gap-4 border-b border-slate-200 bg-white px-6",
    )


def title() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.div(
                rx.el.span(
                    "WORKSPACE",
                    class_name="text-[10px] font-medium tracking-[0.15em] text-slate-500",
                ),
                rx.el.span("/", class_name="text-slate-300"),
                rx.el.span(S.page, class_name="text-[10px] text-slate-500"),
                class_name="mb-2 flex gap-2",
            ),
            rx.el.h1(
                rx.match(
                    S.page,
                    ("Overview", "Antarctic sea ice overview"),
                    ("Map Explorer", "Explore the ice edge"),
                    ("Compare", "Compare conditions"),
                    ("Model Insights", "Patterns beneath the surface"),
                    ("Data", "Data catalogue & CSV workspace"),
                    "About this research workspace",
                ),
                class_name="font-['IBM_Plex_Sans'] text-[26px] leading-tight font-medium tracking-[-0.025em] text-[#172e40]",
            ),
            rx.el.p(
                rx.match(
                    S.page,
                    (
                        "Overview",
                        "Explore seasonal change, environmental conditions and spatial patterns.",
                    ),
                    (
                        "Map Explorer",
                        "A closer look at the Antarctic ocean. Select a region to inspect conditions.",
                    ),
                    (
                        "Compare",
                        "Explore relationships between variables and across seasonal periods.",
                    ),
                    (
                        "Model Insights",
                        "Explore illustrative K-Means groupings — not trained model results.",
                    ),
                    (
                        "Data",
                        "Import, preview and edit shared CSV records — separate from the synthetic scientific demos.",
                    ),
                    "Modelling Antarctic Sea Ice with Supervised Machine Learning and Satellite Data",
                ),
                class_name="mt-2 text-xs text-slate-500",
            ),
        ),
        rx.el.div(
            selector(
                "Year", S.year, ["2017", "2020", "2023", "2024"], S.set_year
            ),
            rx.el.div(
                rx.el.button(
                    "February",
                    on_click=S.set_month(2),
                    class_name=rx.cond(
                        S.month == 2,
                        "px-4 min-h-9 rounded-md bg-[#245f7e] text-white text-xs font-medium",
                        "px-4 min-h-9 rounded-md text-slate-600 text-xs hover:bg-slate-100",
                    ),
                ),
                rx.el.button(
                    "September",
                    on_click=S.set_month(9),
                    class_name=rx.cond(
                        S.month == 9,
                        "px-4 min-h-9 rounded-md bg-[#245f7e] text-white text-xs font-medium",
                        "px-4 min-h-9 rounded-md text-slate-600 text-xs hover:bg-slate-100",
                    ),
                ),
                class_name="flex rounded-lg border border-slate-200 p-1 bg-white",
            ),
            class_name="flex items-center gap-3 self-start pt-5",
        ),
        class_name="mb-5 flex flex-wrap items-center justify-between gap-4",
    )


def metric(
    label: str, value: rx.Var | str, unit: str, foot: str, icon: str
) -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.span(
                label,
                class_name="text-[10px] font-medium tracking-[0.09em] text-slate-500",
            ),
            rx.icon(icon, class_name="h-4 w-4 text-slate-400"),
            class_name="flex justify-between items-center",
        ),
        rx.el.div(
            rx.el.span(
                value,
                class_name="font-['IBM_Plex_Sans'] text-[29px] leading-none font-medium tracking-tight text-[#183d54]",
            ),
            rx.el.span(unit, class_name="text-xs text-slate-500"),
            class_name="mt-3 flex gap-2 items-baseline",
        ),
        rx.el.p(foot, class_name="mt-2 text-[10px] text-slate-500"),
        class_name="bg-white border border-slate-200 rounded-lg px-4 py-3.5",
    )


def metrics() -> rx.Component:
    return rx.el.div(
        metric(
            "SEA ICE EXTENT",
            f"{S.extent:.1f}",
            "million km²",
            "Ocean area with ≥15% ice cover",
            "snowflake",
        ),
        metric(
            "MARGINAL ICE ZONE",
            f"{S.miz:.2f}",
            "million km²",
            "Transition between pack ice & ocean",
            "scan-line",
        ),
        metric(
            "MEAN SEA-SURFACE TEMP.",
            f"{S.temperature:.1f}",
            "°C",
            "Across the illustrative sea ice domain",
            "thermometer",
        ),
        metric(
            "SPATIAL CLUSTERS",
            "4",
            "K-Means",
            "3 environmental variables · demo",
            "network",
        ),
        class_name="mb-4 grid grid-cols-2 xl:grid-cols-4 gap-3",
    )


def layer_row(name: rx.Var) -> rx.Component:
    return rx.el.button(
        rx.icon(
            rx.match(
                name,
                ("Sea ice concentration", "snowflake"),
                ("Marginal Ice Zone", "scan-line"),
                ("Wind speed", "wind"),
                ("ML clusters", "network"),
                "thermometer",
            ),
            class_name="h-4 w-4 text-slate-500",
        ),
        rx.el.span(name, class_name="flex-1 text-left"),
        rx.el.span(
            rx.cond(
                S.layers.contains(name), rx.icon("check", class_name="h-3 w-3")
            ),
            class_name=rx.cond(
                S.layers.contains(name),
                "flex h-4 w-4 items-center justify-center rounded-[4px] bg-[#2d6c8b] border border-[#2d6c8b] text-white",
                "h-4 w-4 rounded-[4px] border border-slate-300 bg-white",
            ),
        ),
        on_click=S.toggle_layer(name),
        aria_pressed=S.layers.contains(name),
        title=rx.cond(
            name == "Marginal Ice Zone",
            "The transition between open ocean and consolidated ice; shown with a patterned boundary.",
            f"Toggle {name} synthetic overlay",
        ),
        class_name="flex w-full items-center gap-2.5 min-h-10 px-1 text-xs text-slate-700 hover:bg-slate-50 rounded focus-visible:outline-2 focus-visible:outline-sky-700",
    )


def inspect() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.h3(
                "Region inspector",
                class_name="text-sm font-semibold text-slate-800",
            ),
            rx.icon("mouse-pointer-2", class_name="h-4 w-4 text-slate-400"),
            class_name="flex items-center justify-between",
        ),
        rx.cond(
            S.region != "",
            rx.el.div(
                rx.el.div(
                    rx.el.p(
                        S.region,
                        class_name="text-sm font-medium text-[#256381]",
                    ),
                    rx.el.button(
                        rx.icon(
                            rx.cond(S.locked, "lock", "lock-open"),
                            class_name="w-3.5 h-3.5",
                        ),
                        rx.cond(S.locked, "Locked", "Lock"),
                        on_click=S.toggle_lock,
                        class_name=BUTTON,
                    ),
                    class_name="flex items-center justify-between mt-4 gap-2",
                ),
                rx.el.p(
                    rx.match(
                        S.region,
                        ("Weddell Sea", "68.2°S, 40.8°W"),
                        ("East Antarctica", "68.4°S, 42.1°E"),
                        ("Ross Sea", "74.1°S, 175.0°E"),
                        "70.2°S, 112.4°W",
                    ),
                    class_name="text-[10px] text-slate-500 mt-1",
                ),
                rx.el.dl(
                    rx.el.div(
                        rx.el.dt("Sea ice concentration"),
                        rx.el.dd(
                            f"{S.concentration:.1f}%",
                            class_name="font-semibold text-slate-800",
                        ),
                        class_name="flex justify-between py-2",
                    ),
                    rx.el.div(
                        rx.el.dt("Sea-surface temperature"),
                        rx.el.dd(
                            f"{S.temperature:.1f} °C",
                            class_name="font-semibold text-slate-800",
                        ),
                        class_name="flex justify-between py-2 border-t border-slate-100",
                    ),
                    rx.el.div(
                        rx.el.dt("Wind speed"),
                        rx.el.dd(
                            f"{S.wind:.1f} m/s",
                            class_name="font-semibold text-slate-800",
                        ),
                        class_name="flex justify-between py-2 border-t border-slate-100",
                    ),
                    class_name="mt-3 text-[11px] text-slate-500",
                ),
                rx.el.button(
                    "Clear selection",
                    on_click=S.clear_region,
                    class_name="text-[11px] text-sky-700 hover:underline min-h-8",
                ),
            ),
            rx.el.div(
                rx.icon("map-pin", class_name="h-6 w-6 text-slate-400 mb-2"),
                rx.el.p(
                    "Where would you like to explore?",
                    class_name="text-xs font-medium text-slate-600",
                ),
                rx.el.p(
                    "Select a region on the map to inspect its local conditions.",
                    class_name="mt-2 text-[11px] leading-relaxed text-slate-500",
                ),
                class_name="py-5",
            ),
        ),
        class_name="p-4 border-t border-slate-200",
    )


def layers_panel() -> rx.Component:
    return rx.el.aside(
        rx.el.div(
            rx.el.div(
                rx.el.h3(
                    "Layers & analysis",
                    class_name="text-sm font-semibold text-slate-800",
                ),
                rx.icon("layers", class_name="h-4 w-4 text-slate-500"),
                class_name="flex items-center justify-between",
            ),
            rx.el.p(
                "Build your view of the Antarctic.",
                class_name="text-[11px] text-slate-500 mt-1",
            ),
            class_name="p-4 border-b border-slate-100",
        ),
        rx.el.div(
            rx.foreach(S.layer_names, layer_row),
            rx.el.div(
                rx.icon("info", class_name="w-3 h-3 shrink-0 mt-0.5"),
                rx.el.p(
                    "Ice edge shown with a patterned boundary, not colour alone."
                ),
                class_name="flex gap-2 rounded-md bg-[#f2f7fa] p-2.5 text-[10px] leading-relaxed text-slate-500 mt-3",
            ),
            class_name="p-4 pt-2",
        ),
        inspect(),
        class_name="bg-white border border-slate-200 rounded-lg min-w-0",
    )


def legend() -> rx.Component:
    return rx.el.div(
        rx.cond(
            S.layers.contains("Sea ice concentration"),
            rx.el.div(
                rx.el.p(
                    "SEA ICE CONCENTRATION",
                    class_name="text-[8px] tracking-[0.08em] font-semibold text-slate-600 mb-1.5",
                ),
                rx.el.div(
                    rx.el.span(class_name="bg-[#eaf5f8] flex-1"),
                    rx.el.span(class_name="bg-[#dbedf4] flex-1"),
                    rx.el.span(class_name="bg-[#c8e1ed] flex-1"),
                    rx.el.span(class_name="bg-[#99c3d8] flex-1"),
                    rx.el.span(class_name="bg-[#538ea9] flex-1"),
                    class_name="flex h-2 w-36 border border-slate-200",
                ),
                rx.el.div(
                    "0",
                    rx.el.span("50"),
                    rx.el.span("100%"),
                    class_name="flex justify-between mt-1 text-[8px] text-slate-500 w-36",
                ),
            ),
        ),
        rx.cond(
            S.layers.contains("Marginal Ice Zone"),
            rx.el.p(
                "┄┄  Marginal Ice Zone",
                class_name="text-[9px] text-[#2c7896] mt-2",
            ),
        ),
        rx.cond(
            S.layers.contains("Wind speed"),
            rx.el.p(
                "↗  Wind · 0–30 m/s", class_name="text-[9px] text-teal-800 mt-1"
            ),
        ),
        rx.cond(
            S.layers.contains("Sea-surface temperature"),
            rx.el.p(
                "▱  SST · −2 to 3 °C",
                class_name="text-[9px] text-amber-800 mt-1",
            ),
        ),
        rx.cond(
            S.layers.contains("Air temperature"),
            rx.el.p(
                "┈  Air · −30 to 0 °C",
                class_name="text-[9px] text-violet-800 mt-1",
            ),
        ),
        rx.cond(
            S.layers.contains("ML clusters"),
            rx.el.p(
                "C1 ━   C2 ▨   C3 ┈   C4 ╌",
                class_name="text-[9px] text-slate-700 mt-1",
            ),
        ),
        class_name="absolute left-4 bottom-3 rounded-md bg-white/90 p-2.5",
    )


def timeline() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.div(
                rx.icon("calendar-days", class_name="h-4 w-4 text-slate-500"),
                rx.el.span(
                    S.date, class_name="text-xs font-semibold text-slate-700"
                ),
                rx.el.span(
                    rx.cond(
                        S.month == 9,
                        "SEASONAL MAXIMUM",
                        rx.cond(
                            S.month == 2, "SEASONAL MINIMUM", "MONTHLY VIEW"
                        ),
                    ),
                    class_name="text-[8px] tracking-wider text-slate-500 bg-slate-100 px-2 py-1 rounded",
                ),
                class_name="flex items-center gap-2",
            ),
            rx.el.span(
                "MONTHLY RESOLUTION",
                class_name="hidden sm:block text-[8px] text-slate-400 tracking-wider",
            ),
            class_name="flex items-center justify-between mb-2",
        ),
        rx.el.div(
            rx.el.button(
                rx.icon("skip-back", class_name="h-3.5 w-3.5"),
                on_click=S.step(-1),
                title="Previous month",
                aria_label="Previous month",
                class_name=BUTTON,
            ),
            rx.el.button(
                rx.icon(
                    rx.cond(S.playing, "pause", "play"),
                    class_name="h-3.5 w-3.5",
                ),
                on_click=S.toggle_play,
                title="Play or pause timeline",
                aria_label="Play or pause timeline",
                class_name="flex items-center justify-center min-h-9 w-9 shrink-0 rounded-md bg-[#245f7e] text-white hover:bg-sky-900",
            ),
            rx.el.button(
                rx.icon("skip-forward", class_name="h-3.5 w-3.5"),
                on_click=S.step(1),
                title="Next month",
                aria_label="Next month",
                class_name=BUTTON,
            ),
            rx.el.div(
                rx.el.input(
                    type="range",
                    min=1,
                    max=12,
                    value=S.month,
                    on_change=S.scrub.throttle(100),
                    aria_label="Timeline month",
                    class_name="w-full accent-[#2c7294] h-4 cursor-pointer",
                ),
                rx.el.div(
                    rx.foreach(
                        S.months,
                        lambda month, i: rx.el.button(
                            month,
                            on_click=S.set_month(i + 1),
                            class_name=rx.cond(
                                S.month == i + 1,
                                "text-[9px] font-semibold text-[#1f607f] min-h-6",
                                "text-[9px] text-slate-500 min-h-6 hover:text-sky-800",
                            ),
                        ),
                    ),
                    class_name="flex justify-between",
                ),
                class_name="flex-1 min-w-0 ml-2",
            ),
            class_name="flex items-start gap-1.5",
        ),
        class_name="border-t border-slate-200 bg-white px-4 py-3 rounded-b-lg",
    )


def map_panel() -> rx.Component:
    return rx.el.section(
        rx.el.div(
            rx.el.div(
                rx.icon("globe", class_name="h-4 w-4 text-[#286180]"),
                rx.el.h2(
                    "Antarctic polar view",
                    class_name="text-sm font-semibold text-slate-800",
                ),
                rx.el.span(
                    "SOUTH POLE · 90°S",
                    class_name="hidden sm:block ml-2 text-[8px] text-slate-400 tracking-wider",
                ),
                class_name="flex items-center gap-2",
            ),
            rx.el.button(
                rx.icon("columns-2", class_name="h-3.5 w-3.5"),
                rx.cond(S.split, "Single view", "Split comparison"),
                on_click=S.toggle_split,
                class_name=BUTTON,
            ),
            class_name="flex justify-between items-center gap-2 px-4 py-2.5 border-b border-slate-200 bg-white rounded-t-lg",
        ),
        rx.el.div(
            rx.cond(
                S.page == "Map Explorer",
                rx.html(
                    S.map_svg,
                    class_name="mx-auto w-full max-w-[720px] h-[570px] [&_svg]:w-full [&_svg]:h-full",
                ),
                rx.html(
                    S.map_svg,
                    class_name="mx-auto w-full max-w-[610px] h-[420px] xl:h-[440px] [&_svg]:w-full [&_svg]:h-full",
                ),
            ),
            rx.el.div(
                rx.el.button(
                    rx.icon("plus", class_name="w-4 h-4"),
                    on_click=S.change_zoom(0.2),
                    title="Zoom in",
                    aria_label="Zoom in",
                    class_name=BUTTON,
                ),
                rx.el.button(
                    rx.icon("minus", class_name="w-4 h-4"),
                    on_click=S.change_zoom(-0.2),
                    title="Zoom out",
                    aria_label="Zoom out",
                    class_name=BUTTON,
                ),
                rx.el.button(
                    rx.icon("maximize", class_name="w-4 h-4"),
                    on_click=S.reset_view,
                    title="Reset view",
                    aria_label="Reset view",
                    class_name=BUTTON,
                ),
                rx.el.button(
                    rx.icon("arrow-left", class_name="w-4 h-4"),
                    on_click=S.move(-20),
                    title="Pan west (simulated)",
                    aria_label="Pan west",
                    class_name=BUTTON,
                ),
                rx.el.button(
                    rx.icon("arrow-right", class_name="w-4 h-4"),
                    on_click=S.move(20),
                    title="Pan east (simulated)",
                    aria_label="Pan east",
                    class_name=BUTTON,
                ),
                rx.el.span(
                    f"{S.zoom:.1f}×",
                    class_name="text-center text-[9px] text-slate-500",
                ),
                class_name="absolute top-4 left-4 flex flex-col gap-1",
            ),
            rx.el.div(
                rx.el.span(class_name="w-1.5 h-1.5 bg-teal-600 rounded-full"),
                "SYNTHETIC OBSERVATIONS",
                class_name="absolute top-4 right-4 flex items-center gap-1.5 text-[8px] tracking-wider text-slate-500",
            ),
            rx.el.button(
                rx.icon("map-pin", class_name="h-3.5 w-3.5"),
                "Weddell Sea",
                on_click=S.select_region("Weddell Sea"),
                title="68.2°S, 40.8°W · Click to inspect demo conditions",
                class_name="absolute top-[28%] left-[29%] flex items-center gap-1 rounded bg-white/90 px-2 min-h-8 text-[9px] text-[#215979] border border-sky-200 hover:bg-sky-100 focus-visible:outline-2 focus-visible:outline-sky-700",
            ),
            rx.el.button(
                rx.icon("map-pin", class_name="h-3.5 w-3.5"),
                "East Antarctica",
                on_click=S.select_region("East Antarctica"),
                title="68.4°S, 42.1°E · Click to inspect demo conditions",
                class_name="absolute top-[53%] right-[13%] flex items-center gap-1 rounded bg-white/90 px-2 min-h-8 text-[9px] text-[#215979] border border-sky-200 hover:bg-sky-100 focus-visible:outline-2 focus-visible:outline-sky-700",
            ),
            rx.el.button(
                rx.icon("map-pin", class_name="h-3.5 w-3.5"),
                "Ross Sea",
                on_click=S.select_region("Ross Sea"),
                title="74.1°S, 175°E · Click to inspect demo conditions",
                class_name="absolute bottom-[22%] left-[44%] flex items-center gap-1 rounded bg-white/90 px-2 min-h-8 text-[9px] text-[#215979] border border-sky-200 hover:bg-sky-100 focus-visible:outline-2 focus-visible:outline-sky-700",
            ),
            legend(),
            rx.el.div(
                rx.el.div(
                    "0 ━━━━━ 1,000 km", class_name="text-[9px] text-slate-600"
                ),
                rx.el.p(
                    "Illustrative polar projection",
                    class_name="text-[8px] mt-1 text-slate-500",
                ),
                class_name="absolute bottom-4 right-4 text-right",
            ),
            class_name="relative bg-[#f4f8fa] overflow-hidden",
        ),
        rx.cond(
            S.split,
            rx.el.div(
                rx.el.div(
                    rx.el.span(
                        f"A · {S.compare_month} {S.compare_year}",
                        class_name="font-medium",
                    ),
                    rx.el.span(f"B · {S.date}", class_name="font-medium"),
                    class_name="flex justify-between text-xs text-slate-600",
                ),
                rx.el.input(
                    type="range",
                    min=15,
                    max=85,
                    value=S.divider,
                    on_change=S.set_divider.throttle(100),
                    aria_label="Split map divider",
                    class_name="w-full accent-sky-800 mt-2",
                ),
                rx.el.div(
                    selector(
                        "Compare month",
                        S.compare_month,
                        ["February", "September"],
                        S.set_compare_month,
                    ),
                    selector(
                        "Compare year",
                        S.compare_year,
                        ["2017", "2020", "2023", "2024"],
                        S.set_compare_year,
                    ),
                    class_name="flex gap-2 mt-1",
                ),
                class_name="border-t border-slate-200 bg-white p-3",
            ),
        ),
        timeline(),
        class_name="border border-slate-200 rounded-lg min-w-0",
    )


def filters() -> rx.Component:
    return rx.el.div(
        rx.icon("list-filter", class_name="h-3 w-3 text-slate-500"),
        rx.el.span("Active layers", class_name="text-[10px] text-slate-500"),
        rx.foreach(
            S.layers,
            lambda name: rx.el.button(
                name,
                rx.icon("x", class_name="w-2.5 h-2.5"),
                on_click=S.toggle_layer(name),
                title=f"Remove {name} layer",
                class_name="inline-flex items-center gap-1.5 bg-[#eaf0f4] text-[#45677c] rounded px-2 min-h-7 text-[9px] hover:bg-slate-200",
            ),
        ),
        rx.cond(
            S.region != "",
            rx.el.button(
                S.region,
                rx.icon("x", class_name="w-3 h-3"),
                on_click=S.clear_region,
                class_name=BUTTON,
            ),
        ),
        class_name="flex flex-wrap items-center gap-2 mb-3",
    )


def trend() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.div(
                rx.el.h3(
                    "The seasonal cycle",
                    class_name="text-sm font-semibold text-slate-800",
                ),
                rx.el.p(
                    "Monthly sea ice extent · million km²",
                    class_name="text-[10px] text-slate-500 mt-1",
                ),
            ),
            rx.el.span(S.year, class_name="text-xs text-[#276383]"),
            class_name="flex justify-between items-center px-4 pt-4",
        ),
        xy.chart(
            xy.line(
                "month", "extent", color="#377fa0", width=2.5, curve="smooth"
            ),
            xy.x_axis(label="Month · February minimum / September maximum"),
            xy.y_axis(label="Million km²"),
            xy.modebar(False),
            xy.interaction_config(navigation=False),
            data=S.trend,
            height="185px",
            class_name="w-full min-w-[300px]",
        ),
        class_name="bg-white border border-slate-200 rounded-lg min-w-0",
    )


def overview() -> rx.Component:
    return rx.el.div(
        metrics(),
        filters(),
        rx.el.div(
            map_panel(),
            layers_panel(),
            class_name="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_280px] gap-4",
        ),
        rx.cond(
            S.page == "Overview",
            rx.el.div(
                trend(),
                rx.el.div(
                    rx.el.div(
                        rx.icon("network", class_name="h-4 w-4 text-[#4b7792]"),
                        rx.el.h3(
                            "From ice to insight",
                            class_name="text-sm font-semibold text-slate-800",
                        ),
                        rx.el.span(
                            "K-MEANS",
                            class_name="ml-auto text-[8px] tracking-wider text-slate-500",
                        ),
                        class_name="flex gap-2 items-center",
                    ),
                    rx.el.p(
                        "Four distinct spatial patterns.",
                        class_name="font-['IBM_Plex_Sans'] text-xl text-[#204762] mt-5",
                    ),
                    rx.el.p(
                        "Explore how sea ice concentration, temperature and wind conditions group together in this synthetic demonstration.",
                        class_name="text-xs leading-relaxed text-slate-500 mt-2 max-w-md",
                    ),
                    rx.el.button(
                        "Explore model insights",
                        rx.icon("arrow-up-right", class_name="h-3.5 w-3.5"),
                        on_click=S.navigate("Model Insights"),
                        class_name="flex items-center gap-2 text-xs font-medium text-[#256080] min-h-10 mt-4 hover:underline",
                    ),
                    class_name="p-4 bg-white border border-slate-200 rounded-lg",
                ),
                class_name="grid grid-cols-1 lg:grid-cols-[1.25fr_1fr] gap-4 mt-4",
            ),
        ),
    )


def compare() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.div(
                rx.el.p(
                    "X VARIABLE",
                    class_name="mb-2 text-[10px] text-slate-500 tracking-wider",
                ),
                selector(
                    "X variable", S.variable_a, S.variables, S.set_variable_a
                ),
            ),
            rx.icon(
                "arrow-left-right", class_name="h-4 w-4 mt-6 text-slate-400"
            ),
            rx.el.div(
                rx.el.p(
                    "Y VARIABLE",
                    class_name="mb-2 text-[10px] text-slate-500 tracking-wider",
                ),
                selector(
                    "Y variable", S.variable_b, S.variables, S.set_variable_b
                ),
            ),
            rx.el.div(
                rx.el.p(
                    "PEARSON r · DEMO", class_name="text-[10px] text-slate-500"
                ),
                rx.el.p(
                    f"{S.correlation:.2f}",
                    class_name="text-2xl font-medium text-[#265d7c]",
                ),
                class_name="ml-auto",
            ),
            rx.el.div(
                rx.el.p(
                    "SYNTHETIC SAMPLES", class_name="text-[10px] text-slate-500"
                ),
                rx.el.p(
                    "160", class_name="text-2xl font-medium text-slate-700"
                ),
            ),
            class_name="flex flex-wrap items-center gap-5 p-5 bg-white border border-slate-200 rounded-lg mb-4",
        ),
        rx.el.div(
            rx.el.div(
                rx.el.h2(
                    "Environmental relationships",
                    class_name="text-base font-semibold text-slate-800",
                ),
                rx.el.span(S.date, class_name="text-xs text-slate-500"),
                class_name="px-5 pt-5 flex justify-between",
            ),
            xy.chart(
                xy.scatter(
                    "x",
                    "y",
                    color="#3b88a0",
                    size=6,
                    opacity=0.65,
                    stroke="#265874",
                    stroke_width=0.5,
                ),
                xy.x_axis(label="Selected x variable"),
                xy.y_axis(label="Selected y variable"),
                xy.modebar(False),
                xy.interaction_config(navigation=False),
                data=S.scatter,
                height="330px",
                class_name="w-full min-w-[300px]",
            ),
            rx.el.div(
                rx.icon("info", class_name="h-4 w-4 shrink-0"),
                rx.el.p(
                    "DEMO INTERPRETATION · Relationships here are deliberately constructed. Correlation describes these synthetic points only; it does not establish causation or a research finding."
                ),
                class_name="flex gap-2 border-t border-slate-200 p-4 text-xs leading-relaxed text-slate-500",
            ),
            class_name=PANEL,
        ),
        rx.el.div(
            rx.el.h2(
                "Seasonal & period comparison",
                class_name="text-lg font-medium text-slate-800",
            ),
            rx.el.p(
                "Reveal differences in the ice edge. Enable split comparison, then drag the divider.",
                class_name="text-xs mt-1 text-slate-500",
            ),
            class_name="my-5",
        ),
        map_panel(),
    )


def cluster_card(
    number: int, pattern: str, summary: str, share: str
) -> rx.Component:
    return rx.el.button(
        rx.el.div(
            rx.el.span(
                f"C{number}  {pattern}", class_name="text-sm font-semibold"
            ),
            rx.el.span(share, class_name="text-xs"),
            class_name="flex justify-between",
        ),
        rx.el.p(summary, class_name="mt-2 text-xs text-left leading-relaxed"),
        on_click=S.select_cluster(number),
        class_name=rx.cond(
            S.cluster == number,
            "w-full p-4 text-[#235b78] bg-[#edf5f8] border border-[#5695b0] rounded-lg focus-visible:outline-2 focus-visible:outline-sky-700",
            "w-full p-4 text-slate-600 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-sky-700",
        ),
    )


def model() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.div(
                rx.el.span(
                    "MODEL",
                    class_name="text-[9px] tracking-wider text-slate-500",
                ),
                rx.el.p(
                    "K-Means clustering",
                    class_name="mt-1 text-sm font-semibold text-slate-800",
                ),
            ),
            rx.el.div(
                rx.el.span(
                    "INPUTS",
                    class_name="text-[9px] tracking-wider text-slate-500",
                ),
                rx.el.p(
                    "Sea ice · SST · Wind",
                    class_name="mt-1 text-sm text-slate-700",
                ),
            ),
            rx.el.div(
                rx.el.span(
                    "SILHOUETTE · DEMO",
                    class_name="text-[9px] tracking-wider text-slate-500",
                ),
                rx.el.p("0.61", class_name="mt-1 text-sm text-slate-700"),
            ),
            rx.el.span(
                rx.icon("circle-check", class_name="h-4 w-4"),
                "Synthetic results loaded",
                class_name="flex gap-2 items-center text-xs text-teal-700 ml-auto",
            ),
            class_name="flex flex-wrap gap-8 border border-slate-200 bg-white p-4 rounded-lg mb-4",
        ),
        rx.el.div(
            map_panel(),
            rx.el.div(
                rx.el.h3(
                    "Cluster summary",
                    class_name="text-base font-semibold text-slate-800",
                ),
                rx.el.p(
                    "Select a pattern to highlight its map sector.",
                    class_name="text-xs text-slate-500",
                ),
                cluster_card(
                    1, "━ Solid", "High concentration · colder surface", "34%"
                ),
                cluster_card(
                    2,
                    "▨ Diagonal",
                    "Lower concentration · stronger winds",
                    "26%",
                ),
                cluster_card(
                    3,
                    "┈ Dotted",
                    "Intermediate concentration · mixed conditions",
                    "22%",
                ),
                cluster_card(
                    4, "╌ Alternating", "Sparse ice · warmer ocean", "18%"
                ),
                class_name="flex flex-col gap-3",
            ),
            class_name="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_280px] gap-4",
        ),
        rx.el.div(
            rx.el.h3(
                f"Cluster {S.cluster} · variable profile",
                class_name="text-base font-medium text-slate-800",
            ),
            rx.el.p(
                rx.match(
                    S.cluster,
                    (1, "Concentration 86% · SST −1.8 °C · wind 8.2 m/s"),
                    (2, "Concentration 52% · SST −0.7 °C · wind 16.1 m/s"),
                    (3, "Concentration 64% · SST −1.1 °C · wind 11.4 m/s"),
                    "Concentration 28% · SST 1.2 °C · wind 9.6 m/s",
                ),
                class_name="text-sm text-[#2f718b] mt-3",
            ),
            rx.el.p(
                "Illustrative cluster means, not feature importance. K-Means is an unsupervised method that groups similar inputs; no model was trained here.",
                class_name="text-xs text-slate-500 mt-3",
            ),
            rx.el.p(
                "Future research methods: Random Forest and Support Vector Machine — not available in this prototype.",
                class_name="text-xs text-slate-500 mt-3",
            ),
            class_name="p-5 mt-4 border border-slate-200 bg-white rounded-lg",
        ),
    )


def data_card(name: str, icon: str, description: str) -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.icon(icon, class_name="w-6 h-6 text-[#397794]"),
            rx.el.span(
                "✓ DEMO READY",
                class_name="text-[9px] tracking-wider text-teal-700 bg-teal-50 rounded px-2 py-1",
            ),
            class_name="flex justify-between",
        ),
        rx.el.h3(name, class_name="text-lg text-slate-800 font-medium mt-5"),
        rx.el.p(
            description,
            class_name="text-xs text-slate-500 leading-relaxed mt-2",
        ),
        rx.el.div(
            action(
                "View metadata", "file-text", S.dataset_action(name, "metadata")
            ),
            action(
                "Replace dataset",
                "refresh-cw",
                S.dataset_action(name, "replace"),
            ),
            class_name="flex flex-wrap gap-2 mt-5",
        ),
        class_name="rounded-lg border border-slate-200 p-5 bg-white",
    )


def data_page() -> rx.Component:
    return rx.el.div(
        uploaded_workspace(),
        rx.el.div(
            rx.el.h2(
                "Synthetic fixtures · original UI demos",
                class_name="text-sm font-semibold text-[#172e40]",
            ),
            rx.el.p(
                "These four unchanged fixtures power the scientific interface. They are not uploaded datasets or editable database records.",
                class_name="mt-1 text-xs leading-relaxed text-slate-500",
            ),
            class_name="mb-4",
        ),
        rx.el.div(
            data_card(
                "Sea ice dataset",
                "snowflake",
                "Monthly synthetic ice extent and concentration. February and September seasonal fixtures.",
            ),
            data_card(
                "Environmental dataset",
                "wind",
                "Illustrative sea-surface temperature, air temperature and wind speed. No satellite observations.",
            ),
            data_card(
                "Topographic dataset",
                "mountain-snow",
                "Hand-drawn Antarctic outline and polar reference grid. Not suitable for navigation or spatial measurement.",
            ),
            data_card(
                "Model output",
                "network",
                "Four manually constructed cluster patterns for demonstrating linked spatial exploration.",
            ),
            class_name="grid grid-cols-1 md:grid-cols-2 gap-4",
        ),
        rx.cond(
            S.notice != "",
            rx.el.div(
                rx.el.h3(S.metadata, class_name="font-medium text-slate-800"),
                rx.el.p(S.notice, class_name="text-sm text-slate-600 mt-2"),
                role="status",
                class_name="mt-5 p-5 bg-white border border-sky-200 rounded-lg",
            ),
        ),
    )


def about() -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.icon("orbit", class_name="h-12 w-12 text-[#3c7b97]"),
            rx.el.h2(
                "A new perspective on Antarctic sea ice.",
                class_name="font-['IBM_Plex_Sans'] text-3xl text-[#1d4259] mt-6",
            ),
            rx.el.p(
                "This high-fidelity design prototype explores how satellite data, environmental variables and machine learning outputs could be brought into one connected research workspace.",
                class_name="text-sm leading-7 text-slate-600 mt-4 max-w-3xl",
            ),
            rx.el.div(
                rx.el.h3(
                    "Explore → Compare → Understand",
                    class_name="text-lg font-medium text-slate-800",
                ),
                rx.el.p(
                    "Start with a seasonal view. Switch February and September, reveal environmental layers, and select a region. Compare variable relationships, then investigate the four illustrative spatial clusters.",
                    class_name="text-sm text-slate-600 leading-7 mt-3",
                ),
                class_name="border-t border-slate-200 mt-8 pt-6",
            ),
            rx.el.div(
                rx.el.h3(
                    "Scientific context & limitations",
                    class_name="text-lg font-medium text-slate-800",
                ),
                rx.el.p(
                    "Sea ice extent describes ocean area with at least 15% ice cover. The Marginal Ice Zone is the transition between open water and consolidated pack ice. K-Means is unsupervised clustering, not a predictive supervised model.",
                    class_name="text-sm text-slate-600 leading-7 mt-3",
                ),
                rx.el.p(
                    "All scientific values, geometries, correlations and model outputs in Overview, Map Explorer, Compare and Model Insights are synthetic. Uploaded CSVs do not feed these calculations. No satellite APIs or machine learning execution are connected. This is not production software or evidence of climate trends.",
                    class_name="text-sm text-slate-600 leading-7 mt-3",
                ),
                class_name="border-t border-slate-200 mt-8 pt-6",
            ),
            rx.el.div(
                rx.el.h3(
                    "CSV uploads & shared storage",
                    class_name="text-lg font-medium text-slate-800",
                ),
                rx.el.p(
                    "The Data tab accepts UTF-8 CSVs with up to 100,000 rows and 10 columns; the existing 5 MB per-file limit still applies. Import a file, select a saved dataset, then preview, edit, add or delete rows and rename or delete datasets. Changes persist after refresh; the four synthetic fixture cards remain separate UI demos.",
                    class_name="mt-3 text-sm leading-7 text-slate-600",
                ),
                rx.el.p(
                    "This is a shared prototype workspace with no authentication or private permissions. Everyone using the prototype can view and edit saved datasets. Upload only non-confidential CSVs, never confidential research or personal data. CSV contents are parsed within the app, not uploaded to an external service. Values are stored as strings; uploads are not validated as scientific observations.",
                    class_name="mt-3 text-sm leading-7 text-slate-600",
                ),
                action("Open CSV workspace", "database", S.navigate("Data")),
                class_name="mb-6 mt-8 border-t border-slate-200 pt-6",
            ),
            action(
                "Return to exploration", "arrow-right", S.navigate("Overview")
            ),
            class_name="p-8 border border-slate-200 rounded-lg bg-white",
        )
    )


def display_options() -> rx.Component:
    return rx.cond(
        S.display_open,
        rx.el.div(
            rx.el.div(
                rx.icon("accessibility", class_name="w-4 h-4"),
                rx.el.span(
                    "Display preferences", class_name="text-sm font-medium"
                ),
                class_name="flex gap-2 items-center",
            ),
            rx.el.div(
                rx.foreach(
                    ["Standard", "High contrast", "Colour vision safe"],
                    lambda mode: rx.el.button(
                        rx.icon(
                            rx.cond(
                                S.display == mode, "circle-check", "circle"
                            ),
                            class_name="h-4 w-4",
                        ),
                        mode,
                        on_click=S.set_display(mode),
                        class_name=BUTTON,
                    ),
                ),
                class_name="flex gap-2 flex-wrap",
            ),
            rx.el.p(
                "Patterns and text labels are always enabled. High contrast strengthens outlines; colour vision safe removes colour from the map.",
                class_name="text-[11px] text-slate-500 w-full",
            ),
            class_name="mb-5 flex flex-wrap items-center justify-between gap-3 border border-slate-200 bg-white rounded-lg p-4 text-slate-700",
        ),
    )


def workspace() -> rx.Component:
    return rx.el.div(
        sidebar(),
        rx.el.div(
            header(),
            rx.el.main(
                display_options(),
                title(),
                rx.match(
                    S.page,
                    ("Overview", overview()),
                    ("Map Explorer", overview()),
                    ("Compare", compare()),
                    ("Model Insights", model()),
                    ("Data", data_page()),
                    about(),
                ),
                class_name="flex-1 w-full min-w-0 overflow-y-auto px-5 py-5 xl:px-7",
            ),
            rx.el.footer(
                rx.icon("flask-conical", class_name="h-3 w-3 shrink-0"),
                "Prototype — scientific visuals are synthetic. Uploaded CSVs are separate, shared stored records.",
                rx.el.span(
                    "NOT FOR SCIENTIFIC USE",
                    class_name="hidden lg:block ml-auto text-[8px] tracking-wider",
                ),
                class_name="flex items-center gap-2 bg-[#f8fafb] border-t border-slate-200 px-6 py-2.5 text-[10px] text-slate-500 shrink-0",
            ),
            class_name="flex min-w-0 flex-1 flex-col",
        ),
        class_name=rx.match(
            S.display,
            (
                "High contrast",
                "flex h-dvh w-full overflow-hidden bg-[#f5f7f9] font-['Inter'] text-slate-950 [&_button]:focus-visible:outline-2 [&_button]:focus-visible:outline-offset-2 [&_button]:focus-visible:outline-sky-800 [&_main]:contrast-125",
            ),
            (
                "Colour vision safe",
                "flex h-dvh w-full overflow-hidden bg-[#f5f7f9] font-['Inter'] text-slate-800 [&_svg[role=img]]:grayscale [&_button]:focus-visible:outline-2 [&_button]:focus-visible:outline-offset-2 [&_button]:focus-visible:outline-sky-800",
            ),
            "flex h-dvh w-full overflow-hidden bg-[#f5f7f9] font-['Inter'] text-slate-800 [&_button]:focus-visible:outline-2 [&_button]:focus-visible:outline-offset-2 [&_button]:focus-visible:outline-sky-800",
        ),
    )
