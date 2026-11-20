"""engraving tier: engraving/etching/woodcut pattern and plate books via the Internet Archive."""
from lib.providers.internetarchive import _clean
from lib.providers.internetarchive import search as _ia_search

QUERY = (
    '(title:(engraving OR etching OR woodcut OR "laser pattern" OR scroll saw) OR subject:(engraving OR '
    'etching OR wood-engraving)) AND mediatype:texts'
)


def search(query: str, limit: int = 20) -> dict:
    combined = f"({_clean(query)}) AND {QUERY}" if _clean(query) else QUERY
    data = _ia_search(combined, limit)
    data["note"] = "engraving & etching pattern books (archive.org, full scans)"
    return data
