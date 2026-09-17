import pandas as pd


KEY_COLUMNS = [
    "station_id",
    "business_date",
    "product",
]


def tolerance_for(station_quantity):
    """
    Reguła biznesowa:
    większa wartość z:
    - 50 litrów
    - 0,5% dostawy

    Założenie MVP:
    procent liczony od ilości przyjętej raportowanej przez stację.
    """
    return max(50.0, abs(float(station_quantity)) * 0.005)


def make_business_key(station_id, date_value, product):
    return (
        f"{station_id}|"
        f"{pd.Timestamp(date_value).strftime('%Y-%m-%d')}|"
        f"{product}"
    )


def aggregate_station(station):
    deliveries = station[
        station["station_quantity"] > 0
    ].copy()

    if deliveries.empty:
        return pd.DataFrame(
            columns=KEY_COLUMNS + [
                "station_quantity",
                "station_source_rows",
            ]
        )

    result = (
        deliveries
        .groupby(
            KEY_COLUMNS,
            as_index=False,
            dropna=False,
        )
        .agg(
            station_quantity=(
                "station_quantity",
                "sum",
            ),
            station_source_rows=(
                "_source_row",
                lambda x: ",".join(
                    str(v) for v in x
                ),
            ),
        )
    )

    return result


def aggregate_sap(sap, status):
    subset = sap[
        sap["status_normalized"] == status
    ].copy()

    if subset.empty:
        return pd.DataFrame(
            columns=KEY_COLUMNS + [
                "sap_quantity",
                "sap_document_count",
                "sap_documents",
                "sap_source_rows",
            ]
        )

    result = (
        subset
        .groupby(
            KEY_COLUMNS,
            as_index=False,
            dropna=False,
        )
        .agg(
            sap_quantity=(
                "sap_quantity",
                "sum",
            ),
            sap_document_count=(
                "document_id",
                "count",
            ),
            sap_documents=(
                "document_id",
                lambda x: ", ".join(
                    str(v) for v in x
                ),
            ),
            sap_source_rows=(
                "_source_row",
                lambda x: ",".join(
                    str(v) for v in x
                ),
            ),
        )
    )

    return result


def exception_row(
    category,
    station_id,
    product,
    station_date,
    sap_date,
    station_quantity,
    sap_quantity,
    sap_documents,
    reason,
):
    station_qty = (
        float(station_quantity)
        if pd.notna(station_quantity)
        else None
    )

    sap_qty = (
        float(sap_quantity)
        if pd.notna(sap_quantity)
        else None
    )

    if station_qty is not None and sap_qty is not None:
        difference = station_qty - sap_qty
        tolerance = tolerance_for(station_qty)
    else:
        difference = None
        tolerance = (
            tolerance_for(station_qty)
            if station_qty is not None
            else None
        )

    base_date = (
        station_date
        if pd.notna(station_date)
        else sap_date
    )

    key = make_business_key(
        station_id,
        base_date,
        product,
    )

    return {
        "category": category,
        "business_key": key,
        "station_id": station_id,
        "product": product,
        "station_date": station_date,
        "sap_date": sap_date,
        "station_quantity": station_qty,
        "sap_quantity": sap_qty,
        "difference_liters": difference,
        "tolerance_liters": tolerance,
        "sap_documents": sap_documents,
        "reason": reason,
    }


def reconcile(station, sap):
    station_agg = aggregate_station(station)

    sap_active = aggregate_sap(
        sap,
        "UTW",
    )

    sap_sto = aggregate_sap(
        sap,
        "STO",
    )

    results = []

    used_station_keys = set()
    used_sap_keys = set()

    # --------------------------------------------------------
    # 1. Uzgodnienie dokładnie tego samego dnia
    # --------------------------------------------------------

    exact = station_agg.merge(
        sap_active,
        on=KEY_COLUMNS,
        how="inner",
    )

    for _, row in exact.iterrows():
        station_key = (
            row["station_id"],
            row["business_date"],
            row["product"],
        )

        used_station_keys.add(station_key)
        used_sap_keys.add(station_key)

        difference = (
            row["station_quantity"]
            - row["sap_quantity"]
        )

        tolerance = tolerance_for(
            row["station_quantity"]
        )

        if abs(difference) <= tolerance:
            category = "MATCH"
            reason = (
                "Station receipt and active SAP delivery agree "
                "within tolerance."
            )
        else:
            category = "QUANTITY_DIFFERENCE"
            reason = (
                "Quantity difference exceeds tolerance "
                f"of {tolerance:.2f} litres."
            )

        results.append(
            exception_row(
                category=category,
                station_id=row["station_id"],
                product=row["product"],
                station_date=row["business_date"],
                sap_date=row["business_date"],
                station_quantity=row["station_quantity"],
                sap_quantity=row["sap_quantity"],
                sap_documents=row["sap_documents"],
                reason=reason,
            )
        )

    # --------------------------------------------------------
    # 2. Niezgodnione rekordy stacyjne
    #    sprawdzamy SAP następnego dnia
    # --------------------------------------------------------

    station_remaining = []

    for _, row in station_agg.iterrows():
        key = (
            row["station_id"],
            row["business_date"],
            row["product"],
        )

        if key not in used_station_keys:
            station_remaining.append(row)

    for station_row in station_remaining:
        next_day = (
            station_row["business_date"]
            + pd.Timedelta(days=1)
        )

        sap_match = sap_active[
            (sap_active["station_id"] == station_row["station_id"])
            & (sap_active["business_date"] == next_day)
            & (sap_active["product"] == station_row["product"])
        ]

        # Tylko SAP jeszcze nieużyty.
        if not sap_match.empty:
            candidate = sap_match.iloc[0]

            sap_key = (
                candidate["station_id"],
                candidate["business_date"],
                candidate["product"],
            )

            if sap_key not in used_sap_keys:
                used_station_keys.add(
                    (
                        station_row["station_id"],
                        station_row["business_date"],
                        station_row["product"],
                    )
                )

                used_sap_keys.add(sap_key)

                difference = (
                    station_row["station_quantity"]
                    - candidate["sap_quantity"]
                )

                tolerance = tolerance_for(
                    station_row["station_quantity"]
                )

                if abs(difference) <= tolerance:
                    reason = (
                        "SAP delivery was posted one day after "
                        "the station receipt. Quantities agree "
                        "within tolerance."
                    )
                else:
                    reason = (
                        "SAP delivery was posted one day after "
                        "the station receipt and the quantity "
                        "difference also exceeds tolerance."
                    )

                results.append(
                    exception_row(
                        category="DATE_SHIFT",
                        station_id=station_row["station_id"],
                        product=station_row["product"],
                        station_date=station_row["business_date"],
                        sap_date=candidate["business_date"],
                        station_quantity=station_row["station_quantity"],
                        sap_quantity=candidate["sap_quantity"],
                        sap_documents=candidate["sap_documents"],
                        reason=reason,
                    )
                )

    # --------------------------------------------------------
    # 3. Rekordy stacji bez aktywnego SAP:
    #    sprawdzamy STO
    # --------------------------------------------------------

    for _, station_row in station_agg.iterrows():
        station_key = (
            station_row["station_id"],
            station_row["business_date"],
            station_row["product"],
        )

        if station_key in used_station_keys:
            continue

        same_day_sto = sap_sto[
            (sap_sto["station_id"] == station_row["station_id"])
            & (
                sap_sto["business_date"]
                == station_row["business_date"]
            )
            & (sap_sto["product"] == station_row["product"])
        ]

        next_day = (
            station_row["business_date"]
            + pd.Timedelta(days=1)
        )

        next_day_sto = sap_sto[
            (sap_sto["station_id"] == station_row["station_id"])
            & (sap_sto["business_date"] == next_day)
            & (sap_sto["product"] == station_row["product"])
        ]

        sto_match = None

        if not same_day_sto.empty:
            sto_match = same_day_sto.iloc[0]

        elif not next_day_sto.empty:
            sto_match = next_day_sto.iloc[0]

        if sto_match is not None:
            results.append(
                exception_row(
                    category="STATION_WITH_STO",
                    station_id=station_row["station_id"],
                    product=station_row["product"],
                    station_date=station_row["business_date"],
                    sap_date=sto_match["business_date"],
                    station_quantity=station_row["station_quantity"],
                    sap_quantity=sto_match["sap_quantity"],
                    sap_documents=sto_match["sap_documents"],
                    reason=(
                        "Station reports a receipt, but the matching "
                        "SAP document has status STO and is therefore "
                        "not treated as an active delivery."
                    ),
                )
            )

            used_station_keys.add(station_key)

        else:
            results.append(
                exception_row(
                    category="ONLY_STATION",
                    station_id=station_row["station_id"],
                    product=station_row["product"],
                    station_date=station_row["business_date"],
                    sap_date=pd.NaT,
                    station_quantity=station_row["station_quantity"],
                    sap_quantity=None,
                    sap_documents=None,
                    reason=(
                        "Station reports a delivery but no matching "
                        "active SAP delivery was found on the same "
                        "day or the following day."
                    ),
                )
            )

            used_station_keys.add(station_key)

    # --------------------------------------------------------
    # 4. Aktywne SAP bez stacji
    # --------------------------------------------------------

    for _, sap_row in sap_active.iterrows():
        sap_key = (
            sap_row["station_id"],
            sap_row["business_date"],
            sap_row["product"],
        )

        if sap_key in used_sap_keys:
            continue

        results.append(
            exception_row(
                category="ONLY_SAP",
                station_id=sap_row["station_id"],
                product=sap_row["product"],
                station_date=pd.NaT,
                sap_date=sap_row["business_date"],
                station_quantity=None,
                sap_quantity=sap_row["sap_quantity"],
                sap_documents=sap_row["sap_documents"],
                reason=(
                    "Active SAP delivery exists but no corresponding "
                    "station receipt was found."
                ),
            )
        )

    result_df = pd.DataFrame(results)

    if not result_df.empty:
        result_df.insert(
            0,
            "incident_id",
            [
                f"INC-{i:05d}"
                for i in range(
                    1,
                    len(result_df) + 1
                )
            ],
        )

    return (
        result_df,
        station_agg,
        sap_active,
        sap_sto,
    )
