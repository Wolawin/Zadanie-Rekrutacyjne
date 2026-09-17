from datetime import datetime
from pathlib import Path

import pandas as pd


BUSINESS_EXCEPTION_CATEGORIES = [
    "QUANTITY_DIFFERENCE",
    "DATE_SHIFT",
    "ONLY_STATION",
    "ONLY_SAP",
    "STATION_WITH_STO",
]


def build_summary(
    station_raw,
    sap_raw,
    station_valid,
    sap_valid,
    result,
    data_quality,
    station_agg,
    sap_active,
    sap_sto,
):
    def count_category(category):
        if result.empty:
            return 0

        return int(
            (result["category"] == category).sum()
        )

    business_exception_total = sum(
        count_category(category)
        for category
        in BUSINESS_EXCEPTION_CATEGORIES
    )

    station_delivery_total = (
        float(
            station_agg["station_quantity"].sum()
        )
        if not station_agg.empty
        else 0.0
    )

    active_sap_total = (
        float(
            sap_active["sap_quantity"].sum()
        )
        if not sap_active.empty
        else 0.0
    )

    values = [
        ("Run timestamp", datetime.now().isoformat(timespec="seconds")),
        ("Station input rows", len(station_raw)),
        ("SAP input rows", len(sap_raw)),
        ("Station valid rows", len(station_valid)),
        ("SAP valid rows", len(sap_valid)),
        ("Station aggregated deliveries", len(station_agg)),
        ("Active SAP aggregated deliveries", len(sap_active)),
        ("STO SAP aggregated deliveries", len(sap_sto)),
        ("MATCH", count_category("MATCH")),
        (
            "QUANTITY_DIFFERENCE",
            count_category("QUANTITY_DIFFERENCE"),
        ),
        ("DATE_SHIFT", count_category("DATE_SHIFT")),
        ("ONLY_STATION", count_category("ONLY_STATION")),
        ("ONLY_SAP", count_category("ONLY_SAP")),
        (
            "STATION_WITH_STO",
            count_category("STATION_WITH_STO"),
        ),
        (
            "Business exceptions total",
            business_exception_total,
        ),
        (
            "Data quality issues",
            len(data_quality),
        ),
        (
            "Station delivery litres",
            station_delivery_total,
        ),
        (
            "Active SAP litres",
            active_sap_total,
        ),
        (
            "Raw volume difference",
            station_delivery_total - active_sap_total,
        ),
    ]

    return pd.DataFrame(
        values,
        columns=["control", "value"],
    )


def write_report(
    output_path: Path,
    station_raw,
    sap_raw,
    station_valid,
    sap_valid,
    result,
    data_quality,
    station_agg,
    sap_active,
    sap_sto,
):
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    summary = build_summary(
        station_raw,
        sap_raw,
        station_valid,
        sap_valid,
        result,
        data_quality,
        station_agg,
        sap_active,
        sap_sto,
    )

    if result.empty:
        matches = result.copy()
        business_exceptions = result.copy()
    else:
        matches = result[
            result["category"] == "MATCH"
        ].copy()

        business_exceptions = result[
            result["category"].isin(
                BUSINESS_EXCEPTION_CATEGORIES
            )
        ].copy()

    with pd.ExcelWriter(
        output_path,
        engine="openpyxl",
    ) as writer:

        summary.to_excel(
            writer,
            sheet_name="Summary",
            index=False,
        )

        business_exceptions.to_excel(
            writer,
            sheet_name="Business Exceptions",
            index=False,
        )

        data_quality.to_excel(
            writer,
            sheet_name="Data Quality",
            index=False,
        )

        matches.to_excel(
            writer,
            sheet_name="Matches",
            index=False,
        )

        station_valid.to_excel(
            writer,
            sheet_name="Station Normalized",
            index=False,
        )

        sap_valid.to_excel(
            writer,
            sheet_name="SAP Normalized",
            index=False,
        )

        # Podstawowe formatowanie Excela
        for sheet_name in writer.book.sheetnames:
            ws = writer.book[sheet_name]

            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions

            for column_cells in ws.columns:
                max_length = 0

                for cell in column_cells:
                    value = cell.value

                    if value is not None:
                        max_length = max(
                            max_length,
                            len(str(value)),
                        )

                width = min(
                    max(max_length + 2, 10),
                    50,
                )

                ws.column_dimensions[
                    column_cells[0].column_letter
                ].width = width

    return summary
