"""expeditions tier: expedition logs & voyage journals via the Internet Archive."""
from lib.providers.internetarchive import _clean
from lib.providers.internetarchive import search as _ia_search

QUERY = (
    '(subject:("voyages and travels" OR "expedition" OR "expeditions" OR "exploration") OR title:(expedition OR "travel journal" OR voyage)) '
    'AND mediatype:texts'
)


def search(query: str, limit: int = 20) -> dict:
    combined = f'({_clean(query)}) AND {QUERY}' if _clean(query) else QUERY
    data = _ia_search(combined, limit)
    data["note"] = "expedition logs & voyage journals (archive.org full scans)"
    return data
