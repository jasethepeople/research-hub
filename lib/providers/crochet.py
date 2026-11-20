"""crochet tier: crochet/knitting/embroidery pattern books via the Internet Archive."""
from lib.providers.internetarchive import _clean
from lib.providers.internetarchive import search as _ia_search

QUERY = (
    '((title:(crochet OR knitting OR embroidery OR tatting OR macrame) AND (pattern OR patterns OR '
    'designs)) OR collection:(crochetpatterns OR craftingheritage)) AND mediatype:texts'
)


def search(query: str, limit: int = 20) -> dict:
    combined = f"({_clean(query)}) AND {QUERY}" if _clean(query) else QUERY
    data = _ia_search(combined, limit)
    data["note"] = "crochet & needlecraft pattern books (archive.org, full scans)"
    return data
