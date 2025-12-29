from app.parsers.csv_parser import CSVParser


def test_csv_parser_basic(tmp_path):
    p = tmp_path / "sample.csv"
    p.write_text("symbol,date,last,prev_close,volume\nABC,2025-12-28,100,90,1000\n")
    parser = CSVParser()
    recs = parser.parse_file(str(p))
    assert len(recs) == 1
    r = recs[0]
    assert r["symbol"] == "ABC"
    assert r["last"] == 100
    assert r["prev_close"] == 90
    assert r["volume"] == 1000
