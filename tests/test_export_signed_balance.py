import export_momentum_service as service


def test_leaf_balance_keeps_deficits_and_deduplicates_same_code():
    rows = [
        {"year": "2026.08", "hsCode": "2710111000", "expDlr": "3000000000", "impDlr": "500000000", "balPayments": "2500000000"},
        {"year": "2026.08", "hsCode": "2710121000", "expDlr": "100000000", "impDlr": "900000000", "balPayments": "-800000000"},
        {"year": "2026.08", "hsCode": "2710121000", "expDlr": "100000000", "impDlr": "900000000", "balPayments": "-800000000"},
        {"year": "2026.07", "hsCode": "2710131000", "expDlr": "1", "balPayments": "9999999999"},
    ]
    assert service._hs_prefix_balance(rows, "2710", "202608") == 1700000000
    item = next(x for x in service._build_items_from_rows(rows, [], "202608") if x["key"] == "petroleum")
    assert item["exportsUsdBillion"] == 3.1
    assert item["importsUsdBillion"] == 1.4
    assert item["tradeBalanceUsdBillion"] == 1.7


def test_all_deficit_leaf_balances_stay_negative_and_parent_avoids_double_count():
    leaves = [
        {"year": "2026.08", "hsCode": "7201100000", "expDlr": "10", "balPayments": "-30"},
        {"year": "2026.08", "hsCode": "7201200000", "expDlr": "20", "balPayments": "-50"},
    ]
    assert service._hs_prefix_balance(leaves, "72", "202608") == -80
    parent = {"year": "2026.08", "hsCode": "72", "expDlr": "30", "balPayments": "-80"}
    assert service._hs_prefix_balance([parent, *leaves], "72", "202608") == -80
