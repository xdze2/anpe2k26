from anpe.tools.naf import _load_csv_index


def test_csv_index_loads():
    index = _load_csv_index()
    assert "71.12B" in index
    assert "Ingénierie" in index["71.12B"]


def test_naf_lookup_unknown_code():
    index = _load_csv_index()
    assert "99.99Z" not in index


def test_naf_search_returns_matches():
    from anpe.tools.naf import _load_csv_index

    index = _load_csv_index()
    words = ["ingénierie"]
    scored = [
        (sum(1 for w in words if w in label.lower()), code, label)
        for code, label in index.items()
    ]
    scored = [(s, c, l) for s, c, l in scored if s > 0]
    assert any("71.12B" == code for _, code, _ in scored)
