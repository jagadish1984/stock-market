from __future__ import annotations
from typing import List, Dict
import os

from app.parsers.base import BaseParser


class BinaryPlaceholderParser(BaseParser):
    """Placeholder for binary formats. Reads header bytes and returns an error indicating spec required.

    When official NSE binary specs are available, replace this logic to decode fields into the
    standardized record structure.
    """

    def parse_file(self, path: str) -> List[Dict]:
        # read a small header to record metadata
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            hdr = fh.read(256)
        # store metadata record so file is not ignored by system, but raise to indicate missing spec
        raise RuntimeError(
            f"Binary file detected ({path}, size={size}). Official binary spec required to parse. Header sample: {hdr[:64]!r}"
        )
