"""flatearth tier: flat-earth, hollow-earth & alternative-cosmology texts, weighted to pre-1900, via archive.org."""
from lib.providers.internetarchive import _clean
from lib.providers.internetarchive import search as _ia_search

QUERY = (
    '(title:("flat earth" OR "plane earth" OR "earth not a globe" OR "hollow earth" OR zetetic) '
    'OR subject:("flat earth" OR zetetic OR "hollow earth")) AND mediatype:texts AND year:[1700 TO 1950]'
)


def search(query: str, limit: int = 20) -> dict:
    combined = f'({_clean(query)}) AND {QUERY}' if _clean(query) else QUERY
    data = _ia_search(combined, limit)
    data["note"] = "flat-earth & zetetic canon, 1700-1950 (archive.org scans)"
    return data
