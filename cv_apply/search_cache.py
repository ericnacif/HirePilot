"""Cache TTL de resultados por fonte (evita repetir HTTP em buscas iguais)."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass

from cv_apply.config import Settings
from cv_apply.filters import SearchFilters
from cv_apply.profile import JobPosting


@dataclass
class _CacheEntry:
    jobs: list[JobPosting]
    expires_at: float


class SearchCache:
    def __init__(self, ttl_seconds: int = 600, max_entries: int = 80):
        self._ttl = ttl_seconds
        self._max = max_entries
        self._data: dict[str, _CacheEntry] = {}
        self._lock = threading.Lock()

    def _prune(self) -> None:
        now = time.time()
        expired = [k for k, v in self._data.items() if v.expires_at <= now]
        for k in expired:
            del self._data[k]
        if len(self._data) > self._max:
            ordered = sorted(self._data.items(), key=lambda kv: kv[1].expires_at)
            for k, _ in ordered[: len(self._data) - self._max]:
                del self._data[k]

    def make_key(self, source: str, settings: Settings, filters: SearchFilters, limit: int) -> str:
        payload = {
            "source": source,
            "keywords": settings.search_keywords,
            "queries": settings.search_queries,
            "location": settings.search_location,
            "workplace": settings.search_workplace,
            "job_type": settings.search_job_type,
            "experience": settings.search_experience,
            "date": settings.search_date_posted,
            "broad": settings.broad_mode,
            "limit": limit,
        }
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()[:24]

    def get(self, key: str) -> list[JobPosting] | None:
        with self._lock:
            self._prune()
            entry = self._data.get(key)
            if not entry or entry.expires_at <= time.time():
                return None
            return [JobPosting.model_validate(j.model_dump()) for j in entry.jobs]

    def set(self, key: str, jobs: list[JobPosting]) -> None:
        with self._lock:
            self._prune()
            self._data[key] = _CacheEntry(
                jobs=[JobPosting.model_validate(j.model_dump()) for j in jobs],
                expires_at=time.time() + self._ttl,
            )


_cache: SearchCache | None = None


def get_search_cache(ttl_seconds: int = 600) -> SearchCache:
    global _cache
    if _cache is None:
        _cache = SearchCache(ttl_seconds=ttl_seconds)
    return _cache
