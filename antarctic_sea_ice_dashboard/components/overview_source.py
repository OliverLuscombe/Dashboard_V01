import reflex as rx
from antarctic_sea_ice_dashboard.states.uploaded_data import (
    UploadedData as D,
    DatasetSummary,
    MappingField,
)


BUTTON = "inline-flex min-h-9 items-center justify-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-xs font-medium text-slate-600 hover:bg-slate-50 hover:text-sky-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-700 disabled:opacity-40 disabled:cursor-not-allowed"
PRIMARY = "inline-flex min-h-9 items-center justify-center gap-2 rounded-md border border-[#245f7e] bg-[#245f7e] px-3 text-xs font-medium text-white hover:bg-sky-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-700 disabled:opacity-40 disabled:cursor-not-allowed"


def mapping_select(field: MappingField) -> rx.Component:
    return rx.el.div(
        rx.el.label(
            field["label"],
            html_for=f"source-{field['name']}",
            class_name="mb-1 block text-[11px] font-medium text-slate-600",
        ),
        rx.el.div(
            rx.el.select(
                rx.el.option("Not provided", value=""),
                rx.foreach(
                    D.columns, lambda column: rx.el.option(column, value=column)
                ),
                id=f"source-{field['name']}",
                name=field["name"],
                default_value=field["value"],
                disabled=D.source_saving | D.loading | D.importing,
                class_name="min-h-9 w-full appearance-none rounded-md border border-slate-200 bg-white py-2 pl-3 pr-8 text-xs text-slate-800 focus-visible:outline-2 focus-visible:outline-sky-700",
            ),
            rx.icon(
                "chevron-down",
                class_name="pointer-events-none absolute right-3 top-3 h-3 w-3 text-slate-500",
            ),
            class_name="relative",
        ),
        key=field["name"],
        class_name="min-w-0",
    )


def fixed_date_input(
    name: str, label: str, value: rx.Var, help_text: str
) -> rx.Component:
    return rx.el.div(
        rx.el.label(
            label,
            html_for=name,
            class_name="mb-1 block text-[11px] font-medium text-slate-600",
        ),
        rx.el.input(
            id=name,
            name=name,
            type="number",
            min=1,
            max=9999 if name == "fixed_year" else 12,
            step=1,
            input_mode="numeric",
            default_value=value,
            key=value,
            aria_describedby=f"{name}-help",
            disabled=D.source_saving | D.loading | D.importing,
            class_name="min-h-9 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-xs text-slate-800 focus-visible:outline-2 focus-visible:outline-sky-700",
        ),
        rx.el.p(
            help_text,
            id=f"{name}-help",
            class_name="mt-1 text-[10px] leading-relaxed text-slate-600",
        ),
        class_name="min-w-0",
    )


def active_source_row(dataset: DatasetSummary) -> rx.Component:
    return rx.el.div(
        rx.el.button(
            rx.el.span(
                dataset["name"],
                class_name="block break-words text-left text-xs font-medium text-slate-800",
            ),
            rx.el.span(
                f"{dataset['snapshot']} · {dataset['rows']:,} rows",
                class_name="mt-1 block text-left text-[10px] text-slate-500",
            ),
            on_click=D.select_dataset(dataset["id"]),
            disabled=D.loading | D.importing | D.source_saving,
            class_name="min-w-0 flex-1 rounded px-2 py-1 text-left hover:bg-slate-50",
        ),
        rx.el.button(
            rx.icon("x", class_name="h-3.5 w-3.5"),
            "Remove layer",
            on_click=D.remove_source(dataset["id"]),
            disabled=D.loading | D.importing | D.source_saving,
            class_name=BUTTON,
        ),
        key=dataset["id"],
        class_name="flex items-center justify-between gap-2 rounded-md border border-slate-200 p-2",
    )


def active_source() -> rx.Component:
    return rx.el.section(
        rx.el.div(
            rx.el.div(
                rx.el.h2(
                    "Active CSV layers",
                    class_name="text-sm font-semibold text-[#172e40]",
                ),
            ),
            class_name="flex items-center justify-between gap-3",
        ),
        rx.el.p(
            "Only CSV datasets you apply are available as globe layers. Multiple active CSV layers can be displayed together within their Year/Month group.",
            class_name="mt-2 text-[11px] leading-relaxed text-slate-600",
        ),
        rx.cond(
            D.active_sources.length() > 0,
            rx.el.div(
                rx.foreach(D.active_sources, active_source_row),
                class_name="mt-3 grid gap-2 sm:grid-cols-2",
            ),
            rx.el.p(
                "No CSV layers are active. Configure a geographic dataset below and apply it.",
                class_name="mt-3 text-xs text-slate-500",
            ),
        ),
        rx.cond(
            D.source_error != "",
            rx.el.p(
                D.source_error,
                role="alert",
                class_name="mt-3 rounded-md border border-red-200 bg-red-50 p-3 text-xs text-red-700",
            ),
        ),
        rx.cond(
            D.source_success != "",
            rx.el.p(
                D.source_success,
                role="status",
                class_name="mt-3 rounded-md border border-green-200 bg-green-50 p-3 text-xs text-green-700",
            ),
        ),
        class_name="mb-4 rounded-lg border border-slate-200 bg-white p-4",
    )


def source_configuration() -> rx.Component:
    return rx.el.section(
        rx.el.div(
            rx.el.h3(
                "Configure this CSV layer",
                class_name="text-sm font-semibold text-[#172e40]",
            ),
            rx.cond(
                D.selected_source_active,
                rx.el.span(
                    "Active layer",
                    class_name="w-fit rounded-md bg-[#edf5f8] px-2 py-1 text-[10px] font-medium text-[#245f7e]",
                ),
            ),
            class_name="flex flex-wrap items-center gap-3",
        ),
        rx.el.p(
            "Map Latitude and Longitude and at least one numeric measurement column. New imports include the date entered before upload; older files may remain undated or be assigned a date here. Applying this file does not deactivate other CSV layers.",
            class_name="mt-2 text-[11px] leading-relaxed text-slate-600",
        ),
        rx.el.form(
            rx.el.div(
                rx.foreach(D.mapping_fields, mapping_select),
                class_name="grid grid-cols-1 gap-3 md:grid-cols-2",
            ),
            rx.el.fieldset(
                rx.el.legend(
                    "Snapshot date metadata · both fields together, or leave both blank",
                    class_name="text-[11px] font-semibold text-[#245f7e]",
                ),
                rx.el.div(
                    fixed_date_input(
                        "fixed_year",
                        "Snapshot year",
                        D.fixed_year,
                        "Optional for older, undated CSVs; use a whole number 1–9999.",
                    ),
                    fixed_date_input(
                        "fixed_month",
                        "Snapshot month",
                        D.fixed_month,
                        "Optional for older, undated CSVs; use a whole number 1–12.",
                    ),
                    class_name="mt-2 grid grid-cols-1 gap-3 md:grid-cols-2",
                ),
                class_name="mt-4 rounded-md border border-slate-200 bg-[#f4f8fa] p-3",
            ),
            rx.el.div(
                rx.el.button(
                    rx.cond(
                        D.source_saving,
                        rx.icon(
                            "loader-circle",
                            class_name="h-3.5 w-3.5 animate-spin",
                        ),
                        rx.icon("save", class_name="h-3.5 w-3.5"),
                    ),
                    rx.cond(
                        D.source_saving,
                        "Saving…",
                        rx.cond(
                            D.selected_source_active,
                            "Save mapping and keep active",
                            "Apply as CSV layer",
                        ),
                    ),
                    type="submit",
                    disabled=D.source_saving | D.loading | D.importing,
                    class_name=PRIMARY,
                ),
                rx.cond(
                    D.selected_source_active,
                    rx.el.button(
                        "Remove from map",
                        type="button",
                        on_click=D.remove_source(D.selected_id),
                        disabled=D.source_saving | D.loading | D.importing,
                        class_name=BUTTON,
                    ),
                ),
                rx.el.button(
                    "Restore header suggestions",
                    type="button",
                    on_click=D.suggest_source,
                    disabled=D.source_saving | D.loading | D.importing,
                    class_name=BUTTON,
                ),
                class_name="mt-4 flex flex-wrap gap-2",
            ),
            rx.cond(
                D.source_error != "",
                rx.el.p(
                    D.source_error,
                    role="alert",
                    class_name="mt-3 rounded-md border border-red-200 bg-red-50 p-3 text-xs text-red-700",
                ),
            ),
            key=D.mapping_revision,
            on_submit=D.apply_source,
            class_name="mt-4",
        ),
        rx.el.p(
            "Applying adds this CSV alongside other active layers. Mapping edits stay unsaved until applied. Snapshot groups are selected in Map Explorer.",
            class_name="mt-2 text-[10px] leading-relaxed text-slate-600",
        ),
        class_name="border-b border-slate-200 p-4",
    )
