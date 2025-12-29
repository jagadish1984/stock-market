Where to plug in NSE official binary specs

The `app/parsers/binary_placeholder.py` contains code that will raise a clear error when a binary file is encountered. Once you obtain official NSE binary format specifications (field offsets, types, record lengths), replace the placeholder `parse_file` implementation with code that:

- Opens the file in binary mode
- Iterates records according to the documented layout
- Decodes fields (symbol, date, time, price, qty, side, etc.)
- Maps to the standardized dict fields used by the CSV parser

Keep tests and incremental parsing handy to verify correctness. Store parsed rows into the database following the same logic used in `app/ingest.py`.
