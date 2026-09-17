from pathlib import Path
import sys
import traceback

import pandas as pd

from validation import load_and_profile
from normalization import (
    normalize_station,
    normalize_sap,
)
from reconciliation import reconcile
from reporting import write_report


BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"

STATION_FILE = (
    DATA_DIR / "stacje_raport_dobowy.csv"
)

SAP_FILE = (
    DATA_DIR / "sap_dostawy.csv"
)

OUTPUT_FILE = (
    OUTPUT_DIR / "reconciliation_result.xlsx"
)


def combine_quality_frames(*frames):
    valid_frames = [
        frame
        for frame in frames
        if frame is not None
        and not frame.empty
    ]

    if not valid_frames:
        return pd.DataFrame(
            columns=[
                "source",
                "issue_type",
                "row_number",
                "business_key",
                "field",
                "raw_value",
                "reason",
            ]
        )

    return pd.concat(
        valid_frames,
        ignore_index=True,
    )


def get_quality_keys(data_quality, source):
    """
    Zwraca pełne klucze biznesowe, dla których problemy
    jakości danych mogą uniemożliwiać uzgodnienie.

    Klucz pełny ma format:
    STxxxx|YYYY-MM-DD|PRODUCT
    """
    if data_quality.empty:
        return set()

    subset = data_quality[
        data_quality["source"] == source
    ]

    keys = set()

    for value in subset["business_key"].dropna():
        value = str(value)

        if value.count("|") == 2:
            keys.add(value)

    return keys


def block_false_business_exceptions(
    result,
    data_quality,
):
    """
    Jeżeli pozorny ONLY_STATION / ONLY_SAP wynika z tego,
    że rekord drugiej strony został poddany kwarantannie
    z powodu Data Quality, nie pokazujemy go jako zwykłego
    wyjątku biznesowego.

    Zamiast tego dodajemy sygnał:
    RECONCILIATION_BLOCKED_BY_DATA_QUALITY.
    """

    if result.empty:
        return result, data_quality

    sap_quality_keys = get_quality_keys(
        data_quality,
        "SAP",
    )

    station_quality_keys = get_quality_keys(
        data_quality,
        "STATION",
    )

    blocked_indexes = []
    new_quality_rows = []

    for index, row in result.iterrows():

        category = row["category"]
        business_key = row["business_key"]

        # ---------------------------------------------
        # Stacja ma dostawę, ale SAP został
        # wyłączony z reconciliation przez Data Quality
        # ---------------------------------------------

        if (
            category == "ONLY_STATION"
            and business_key in sap_quality_keys
        ):
            blocked_indexes.append(index)

            new_quality_rows.append(
                {
                    "source": "RECONCILIATION",
                    "issue_type":
                        "RECONCILIATION_BLOCKED_BY_DATA_QUALITY",
                    "row_number": None,
                    "business_key": business_key,
                    "field": "business_key",
                    "raw_value": category,
                    "reason": (
                        "Station delivery cannot be classified as "
                        "ONLY_STATION because SAP contains data for "
                        "the same business key that was quarantined "
                        "due to a data-quality problem. Manual "
                        "clarification is required."
                    ),
                }
            )

        # ---------------------------------------------
        # SAP ma dostawę, ale rekord stacyjny został
        # wyłączony przez Data Quality
        # ---------------------------------------------

        elif (
            category == "ONLY_SAP"
            and business_key in station_quality_keys
        ):
            blocked_indexes.append(index)

            new_quality_rows.append(
                {
                    "source": "RECONCILIATION",
                    "issue_type":
                        "RECONCILIATION_BLOCKED_BY_DATA_QUALITY",
                    "row_number": None,
                    "business_key": business_key,
                    "field": "business_key",
                    "raw_value": category,
                    "reason": (
                        "SAP delivery cannot be classified as "
                        "ONLY_SAP because station data exists for "
                        "the same business key but was quarantined "
                        "due to a data-quality problem. Manual "
                        "clarification is required."
                    ),
                }
            )

    if blocked_indexes:
        result = result.drop(
            index=blocked_indexes
        ).reset_index(drop=True)

    if new_quality_rows:
        new_quality_df = pd.DataFrame(
            new_quality_rows
        )

        data_quality = pd.concat(
            [
                data_quality,
                new_quality_df,
            ],
            ignore_index=True,
        )

    # Po usunięciu zablokowanych przypadków
    # numerujemy incydenty ponownie.
    if not result.empty:
        result["incident_id"] = [
            f"INC-{i:05d}"
            for i in range(
                1,
                len(result) + 1
            )
        ]

    return result, data_quality


def main():
    print("=" * 80)
    print("FUEL DELIVERY RECONCILIATION")
    print("=" * 80)

    try:

        # ====================================================
        # STEP 1
        # ====================================================

        print(
            "\nSTEP 1 - Loading and profiling input files"
        )

        station_raw, station_profile = (
            load_and_profile(
                STATION_FILE,
                "Station daily report",
            )
        )

        sap_raw, sap_profile = (
            load_and_profile(
                SAP_FILE,
                "SAP deliveries",
            )
        )

        # ====================================================
        # STEP 2
        # ====================================================

        print(
            "\nSTEP 2 - Normalization and data quality"
        )

        station_valid, station_quality = (
            normalize_station(
                station_raw
            )
        )

        sap_valid, sap_quality = (
            normalize_sap(
                sap_raw
            )
        )

        data_quality = combine_quality_frames(
            station_quality,
            sap_quality,
        )

        print(
            f"Station valid rows: "
            f"{len(station_valid)}"
        )

        print(
            f"SAP valid rows: "
            f"{len(sap_valid)}"
        )

        print(
            f"Initial data quality signals: "
            f"{len(data_quality)}"
        )

        # ====================================================
        # STEP 3
        # ====================================================

        print(
            "\nSTEP 3 - Delivery reconciliation"
        )

        (
            result,
            station_agg,
            sap_active,
            sap_sto,
        ) = reconcile(
            station_valid,
            sap_valid,
        )

        # ====================================================
        # STEP 3A
        # Nie pozwalamy Data Quality generować fałszywych
        # ONLY_STATION / ONLY_SAP
        # ====================================================

        result, data_quality = (
            block_false_business_exceptions(
                result,
                data_quality,
            )
        )

        if not result.empty:
            print(
                "\nReconciliation categories:"
            )

            print(
                result["category"]
                .value_counts()
                .to_string()
            )

        print(
            f"\nFinal data quality signals: "
            f"{len(data_quality)}"
        )

        # ====================================================
        # STEP 4
        # ====================================================

        print(
            "\nSTEP 4 - Creating Excel report"
        )

        summary = write_report(
            OUTPUT_FILE,
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

        print("\n" + "=" * 80)
        print(
            "PROCESS COMPLETED SUCCESSFULLY"
        )
        print("=" * 80)

        print(
            f"\nOutput: {OUTPUT_FILE}"
        )

        print(
            "\nCONTROL SUMMARY:"
        )

        print(
            summary.to_string(
                index=False
            )
        )

    except Exception as exc:

        print("\n" + "=" * 80)
        print("PROCESS FAILED")
        print("=" * 80)

        print(str(exc))
        print()

        traceback.print_exc()

        sys.exit(1)


if __name__ == "__main__":
    main()
