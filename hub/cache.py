import time
from collections import OrderedDict
from copy import deepcopy
from typing import Any

CACHE_TTL = 900
CACHE_MAXSIZE = 500


class ResponseCache:
    def __init__(self, ttl: int = CACHE_TTL, maxsize: int = CACHE_MAXSIZE):
        self.ttl = ttl
        self.maxsize = maxsize
        self._items: OrderedDict[tuple[str, ...], tuple[float, Any]] = OrderedDict()

    def get(self, key: tuple[str, ...]) -> Any | None:
        entry = self._items.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at <= time.monotonic():
            del self._items[key]
            return None
        self._items.move_to_end(key)
        return deepcopy(value)

    def put(self, key: tuple[str, ...], value: Any):
        self._items[key] = (time.monotonic() + self.ttl, deepcopy(value))
        self._items.move_to_end(key)
        while len(self._items) > self.maxsize:
            self._items.popitem(last=False)

    def __len__(self) -> int:
        return len(self._items)
