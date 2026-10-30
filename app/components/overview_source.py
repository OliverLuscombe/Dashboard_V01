import reflex as rx
from app.states.uploaded_data import UploadedData as D, MappingField, GRID_ROWS


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


def active_mapping_row(field: MappingField) -> rx.Component:
    return rx.el.div(
        rx.el.dt(field["label"], class_name="text-[10px] text-slate-500"),
        rx.el.dd(
            field["value"],
            class_name="break-words text-[11px] font-medium text-slate-700",
        ),
        key=field["name"],
        class_name="min-w-0",
    )


def active_source() -> rx.Component:
    return rx.el.section(
        rx.el.div(
            rx.el.div(
                rx.el.h2(
                    "Overview source · saved configuration",
                    class_name="text-sm font-semibold text-[#172e40]",
                ),
                rx.el.p(
                    rx.cond(
                        D.active_source_id > 0,
                        f"Active dataset: {D.active_source_name}",
                        "No uploaded Overview source selected",
                    ),
                    class_name="mt-1 break-words text-xs font-medium text-[#245f7e]",
                ),
            ),
            rx.cond(
                D.active_source_id > 0,
                rx.el.div(
                    rx.el.button(
                        "Edit active mapping",
                        on_click=D.select_dataset(D.active_source_id),
                        disabled=D.source_saving | D.loading | D.importing,
                        class_name=BUTTON,
                    ),
                    rx.el.button(
                        "Remove Overview source",
                        on_click=D.remove_source,
                        disabled=D.source_saving | D.loading | D.importing,
                        class_name=BUTTON,
                    ),
                    class_name="flex flex-wrap gap-2",
                ),
            ),
            class_name="flex flex-wrap items-center justify-between gap-3",
        ),
        rx.el.p(
            "A CSV is designated for Overview only when you explicitly apply it. Return to Overview to render its mapped readings on the 316-column × 332-row pixel grid and inspect saved pixels. Refresh the Overview map after editing data. Mapped years/months filter the grid, summaries and inspector. Monthly concentration analysis requires mapped month and concentration columns with at least two observed months; other demo pages remain synthetic.",
            class_name="mt-2 text-[11px] leading-relaxed text-slate-600",
        ),
        rx.cond(
            D.active_source_id > 0,
            rx.el.details(
                rx.el.summary(
                    "View persisted active mapping",
                    class_name="cursor-pointer text-xs font-medium text-[#245f7e] focus-visible:outline-2 focus-visible:outline-sky-700",
                ),
                rx.el.dl(
                    rx.foreach(D.active_mapping, active_mapping_row),
                    class_name="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3",
                ),
                class_name="mt-3 border-t border-slate-200 pt-3",
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
                "Configure this dataset for Overview",
                class_name="text-sm font-semibold text-[#172e40]",
            ),
            rx.cond(
                D.selected_source_active,
                rx.el.span(
                    "Active source",
                    class_name="w-fit rounded-md bg-[#edf5f8] px-2 py-1 text-[10px] font-medium text-[#245f7e]",
                ),
            ),
            class_name="flex flex-wrap items-center gap-3",
        ),
        rx.el.p(
            "Map your CSV headers to the fields below. Suggestions ignore case, spaces and punctuation; arbitrary headers can be selected manually. Review units before applying. Year and month must be numeric integers (year 1–9999, month 1–12); invalid mapped dates are excluded. Either date column may be omitted, and no date columns gives an undated snapshot. Missing measurements and dates may be Not provided; no values or latitude/longitude metadata will be invented. A CSV has at most 10 columns, so not every field can be present together.",
            class_name="mt-2 text-[11px] leading-relaxed text-slate-600",
        ),
        rx.el.form(
            rx.el.label(
                "Pixel-coordinate source",
                html_for="coordinate-mode",
                class_name="mb-1 block text-[11px] font-medium text-slate-600",
            ),
            rx.el.div(
                rx.el.select(
                    rx.el.option(
                        "Use mapped x_coordinate and y_coordinate columns",
                        value="columns",
                    ),
                    rx.el.option(
                        "Generate from row order · complete 332 × 316 grid only",
                        value="row_order",
                        disabled=D.row_count != GRID_ROWS,
                    ),
                    id="coordinate-mode",
                    name="coordinate_mode",
                    default_value=D.coordinate_mode,
                    disabled=D.source_saving | D.loading | D.importing,
                    class_name="min-h-9 w-full appearance-none rounded-md border border-slate-200 bg-white py-2 pl-3 pr-8 text-xs text-slate-800 focus-visible:outline-2 focus-visible:outline-sky-700",
                ),
                rx.icon(
                    "chevron-down",
                    class_name="pointer-events-none absolute right-3 top-3 h-3 w-3 text-slate-500",
                ),
                class_name="relative",
            ),
            rx.el.p(
                rx.cond(
                    D.row_count == GRID_ROWS,
                    "104,912 rows: row-order generation is available if saved positions are intact. In that mode, x/y column selections are ignored.",
                    "Map both x and y. Row-order generation is available only for exactly 104,912 rows (332 × 316).",
                ),
                class_name="mt-2 text-[10px] leading-relaxed text-slate-500",
            ),
            rx.el.div(
                rx.foreach(D.mapping_fields, mapping_select),
                class_name="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2",
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
                            "Re-save mapping · use on Overview",
                            "Apply · use on Overview",
                        ),
                    ),
                    type="submit",
                    disabled=D.source_saving | D.loading | D.importing,
                    class_name=PRIMARY,
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
            key=D.mapping_revision,
            on_submit=D.apply_source,
            class_name="mt-4",
        ),
        rx.el.div(
            rx.el.p(
                "Pixel-grid positioning, NOT a real latitude/longitude stereographic transformation.",
                class_name="text-[11px] font-medium text-[#245f7e]",
            ),
            rx.el.p(
                "Row-order mode uses zero-based saved row_position: x = (row_position % 316) + 1; y = 332 − (row_position // 316). Positions 0 → (1, 332), 315 → (316, 332), 316 → (1, 331), 104,911 → (316, 1). Rows run left-to-right, then top-to-bottom. Use only a CSV exported in this exact grid order; no coordinates are written into the CSV or generated for other sizes.",
                class_name="mt-1 text-[10px] leading-relaxed text-slate-600",
            ),
            rx.el.p(
                "Applying replaces the previously active source for everyone. Mapping edits stay unsaved until applied; changing dataset/page or refreshing resets the form. Remove a row-order source before adding or deleting rows. Deleting its dataset also removes the active selection.",
                class_name="mt-2 text-[10px] leading-relaxed text-slate-600",
            ),
            class_name="mt-4 rounded-md border border-slate-200 bg-[#f4f8fa] p-3",
        ),
        class_name="border-b border-slate-200 p-4",
    )
