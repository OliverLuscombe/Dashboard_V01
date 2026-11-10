import reflex as rx

from antarctic_sea_ice_dashboard.states.snapshot_comparison import (
    SnapshotComparison as Compare,
)


BUTTON = "inline-flex min-h-9 items-center justify-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-xs font-medium text-slate-600 hover:bg-slate-50 hover:text-sky-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-700 disabled:opacity-40 disabled:cursor-not-allowed"


def snapshot_selector(
    label: str,
    element_id: str,
    value: rx.Var,
    event: rx.event.EventType,
    allow_empty: bool = False,
) -> rx.Component:
    return rx.el.label(
        rx.el.span(
            label, class_name="mb-1 block text-[11px] font-medium text-slate-600"
        ),
        rx.el.select(
            rx.cond(
                allow_empty,
                rx.el.option("Choose a snapshot", value=""),
            ),
            rx.foreach(
                Compare.groups,
                lambda group: rx.el.option(
                    group["label"], value=group["key"]
                ),
            ),
            id=element_id,
            value=value,
            on_change=event,
            disabled=Compare.loading | (Compare.groups.length() == 0),
            class_name="min-h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-xs text-slate-700 focus-visible:outline-2 focus-visible:outline-sky-700 disabled:opacity-70",
        ),
        class_name="min-w-0 flex-1",
    )


def comparison_card(
    title: str,
    period: rx.Var,
    mean: rx.Var,
    count: rx.Var,
    files: rx.Var,
    tone: str,
) -> rx.Component:
    return rx.el.section(
        rx.el.p(title, class_name="text-[10px] font-semibold tracking-wide text-slate-500"),
        rx.el.p(
            period,
            class_name="mt-1 text-xs font-medium text-[#245f7e]",
        ),
        rx.el.p(
            mean,
            class_name=f"mt-3 break-words text-2xl font-semibold {tone}",
        ),
        rx.el.p(
            count,
            " valid observations · ",
            files,
            " mapped CSV files",
            class_name="mt-2 text-[10px] leading-relaxed text-slate-500",
        ),
        class_name="min-w-0 rounded-lg border border-slate-200 bg-white p-4",
    )


def difference_globe() -> rx.Component:
    return rx.el.section(
        rx.el.div(
            rx.el.div(
                rx.icon("globe", class_name="h-4 w-4 text-[#286180]"),
                rx.el.h2(
                    "Spatial difference on the south-polar globe",
                    class_name="text-sm font-semibold text-slate-800",
                ),
                class_name="flex items-center gap-2",
            ),
            rx.el.p(
                "Each marker compares the mean value in a geographic cell. Blue indicates a decrease, red an increase, and neutral grey is near zero.",
                class_name="mt-1 text-[11px] leading-relaxed text-slate-600",
            ),
            class_name="border-b border-slate-200 bg-white p-4",
        ),
        rx.cond(
            Compare.comparable_cells > 0,
            rx.el.div(
                rx.el.div(
                    id="snapshot-difference-globe",
                    data_globe_source=rx.get_upload_url(
                        Compare.globe_filename
                    ),
                    data_globe_mode="difference",
                    data_globe_periods=Compare.period_a
                    + " → "
                    + Compare.period_b,
                    role="application",
                    aria_label="South-polar globe showing measurement differences between two selected snapshots. Blue is a decrease, red is an increase.",
                    class_name="h-[420px] w-full bg-[#dbe8ed] sm:h-[520px]",
                ),
                rx.el.div(
                    rx.el.span(
                        "−",
                        Compare.globe_max_abs,
                        " ",
                        Compare.measurement_units,
                        class_name="text-[10px] font-medium text-slate-600",
                    ),
                    rx.el.div(
                        class_name="h-3 flex-1 rounded-full bg-[linear-gradient(90deg,#26699a_0%,#f2f4f6_50%,#be3830_100%)]",
                    ),
                    rx.el.span(
                        "+",
                        Compare.globe_max_abs,
                        " ",
                        Compare.measurement_units,
                        class_name="text-[10px] font-medium text-slate-600",
                    ),
                    class_name="flex items-center gap-3 border-t border-slate-200 bg-white px-4 py-3",
                ),
                class_name="overflow-hidden rounded-b-lg border border-t-0 border-slate-200",
            ),
            rx.el.p(
                "No geographic cells contain valid readings in both snapshots, so there is no spatial difference to render.",
                role="status",
                class_name="border-t border-slate-200 bg-[#f8fafb] p-5 text-xs leading-relaxed text-slate-600",
            ),
        ),
        rx.el.p(
            f"{Compare.comparable_cells:,} matched cells · 0.5° latitude × 1° longitude bins. Each cell shows the second snapshot mean minus the first; unmatched cells are not drawn.",
            class_name="border-t border-slate-200 bg-white px-4 py-3 text-[10px] leading-relaxed text-slate-500",
        ),
        class_name="mt-4 overflow-hidden rounded-lg border border-slate-200 bg-white",
    )


def snapshot_comparison() -> rx.Component:
    return rx.el.div(
        rx.el.section(
            rx.el.div(
                rx.el.div(
                    rx.icon("columns-2", class_name="h-4 w-4 text-[#286180]"),
                    rx.el.h2(
                        "Compare uploaded snapshots",
                        class_name="text-sm font-semibold text-slate-800",
                    ),
                    class_name="flex items-center gap-2",
                ),
                rx.el.button(
                    rx.icon("refresh-cw", class_name="h-3.5 w-3.5"),
                    "Refresh comparison",
                    on_click=Compare.refresh,
                    disabled=Compare.loading,
                    class_name=BUTTON,
                ),
                class_name="flex flex-wrap items-center justify-between gap-3",
            ),
            rx.el.p(
                "Choose any two mapped Year/Month snapshots. You can compare different months from the same year. Values are pooled from all mapped CSVs in each snapshot, whether or not those files are active on Map Explorer.",
                class_name="mt-2 text-[11px] leading-relaxed text-slate-600",
            ),
            rx.el.div(
                snapshot_selector(
                    "First snapshot",
                    "compare-period-a",
                    Compare.period_a,
                    Compare.select_period_a,
                ),
                snapshot_selector(
                    "Second snapshot",
                    "compare-period-b",
                    Compare.period_b,
                    Compare.select_period_b,
                    allow_empty=True,
                ),
                rx.el.label(
                    rx.el.span(
                        "Shared measurement",
                        class_name="mb-1 block text-[11px] font-medium text-slate-600",
                    ),
                    rx.el.select(
                        rx.foreach(
                            Compare.measurements,
                            lambda measurement: rx.el.option(
                                measurement["label"],
                                value=measurement["key"],
                            ),
                        ),
                        id="compare-measurement",
                        value=Compare.measurement_key,
                        on_change=Compare.select_measurement,
                        disabled=Compare.loading
                        | (Compare.measurements.length() == 0),
                        class_name="min-h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-xs text-slate-700 focus-visible:outline-2 focus-visible:outline-sky-700 disabled:opacity-70",
                    ),
                    class_name="min-w-0 flex-1",
                ),
                class_name="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3",
            ),
            rx.cond(
                Compare.loading,
                rx.el.p(
                    Compare.message,
                    role="status",
                    class_name="mt-3 text-xs text-slate-500",
                ),
                rx.cond(
                    Compare.error,
                    rx.el.p(
                        Compare.message,
                        role="alert",
                        class_name="mt-3 text-xs leading-relaxed text-red-700",
                    ),
                    rx.el.p(
                        Compare.message,
                        role="status",
                        class_name="mt-3 text-xs leading-relaxed text-slate-600",
                    ),
                ),
            ),
            class_name="rounded-lg border border-slate-200 bg-white p-4",
        ),
        rx.cond(
            (Compare.period_a != "")
            & (Compare.period_b != "")
            & (Compare.loading == False)
            & (Compare.error == False),
            rx.el.div(
                comparison_card(
                    "FIRST SNAPSHOT",
                    Compare.period_a,
                    Compare.mean_a,
                    Compare.count_a,
                    Compare.files_a,
                    "text-[#245f7e]",
                ),
                comparison_card(
                    "SECOND SNAPSHOT",
                    Compare.period_b,
                    Compare.mean_b,
                    Compare.count_b,
                    Compare.files_b,
                    "text-[#245f7e]",
                ),
                rx.el.section(
                    rx.el.p(
                        "CHANGE · SECOND − FIRST",
                        class_name="text-[10px] font-semibold tracking-wide text-slate-500",
                    ),
                    rx.el.p(
                        Compare.difference,
                        class_name="mt-3 break-words text-2xl font-semibold text-[#183d54]",
                    ),
                    rx.el.p(
                        Compare.measurement_label,
                        class_name="mt-2 text-[10px] text-slate-500",
                    ),
                    class_name="min-w-0 rounded-lg border border-sky-100 bg-[#f4f8fa] p-4",
                ),
                class_name="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-3",
            ),
        ),
        rx.el.p(
            "Means use valid numeric readings with valid geographic coordinates. Fraction-form sea-ice concentration (0–1) is converted to percent per CSV. The difference is the second snapshot mean minus the first; no interpolation or area-weighted extent is calculated.",
            class_name="mt-3 text-[10px] leading-relaxed text-slate-500",
        ),
        rx.cond(
            (Compare.period_a != "")
            & (Compare.period_b != "")
            & (Compare.loading == False)
            & (Compare.error == False),
            difference_globe(),
        ),
        class_name="space-y-3",
    )
