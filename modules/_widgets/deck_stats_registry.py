from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from aqt import mw


@dataclass(frozen=True)
class DeckStatEntry:
    label: str
    enabled: bool
    tracked: int
    free: int
    order: int = 100


ProviderFn = Callable[[], DeckStatEntry | dict | None]
_PROVIDERS: dict[str, tuple[int, ProviderFn]] = {}


def register_provider(provider_id: str, provider: ProviderFn, *, order: int = 100) -> None:
    pid = str(provider_id or "").strip()
    if not pid or not callable(provider):
        return
    _PROVIDERS[pid] = (int(order), provider)


def unregister_provider(provider_id: str) -> None:
    pid = str(provider_id or "").strip()
    if not pid:
        return
    _PROVIDERS.pop(pid, None)


def _normalize_entry(raw, *, default_order: int = 100) -> DeckStatEntry | None:
    if isinstance(raw, DeckStatEntry):
        return raw
    if not isinstance(raw, dict):
        return None
    label = str(raw.get("label", "") or "").strip()
    if not label:
        return None
    try:
        order = int(raw.get("order", default_order))
    except Exception:
        order = int(default_order)
    try:
        tracked = int(raw.get("tracked", 0))
    except Exception:
        tracked = 0
    try:
        free = int(raw.get("free", 0))
    except Exception:
        free = 0
    return DeckStatEntry(
        label=label,
        enabled=bool(raw.get("enabled", False)),
        tracked=max(0, tracked),
        free=max(0, free),
        order=order,
    )


def collect_entries() -> list[DeckStatEntry]:
    out: list[DeckStatEntry] = []
    for provider_id, (order, provider) in sorted(_PROVIDERS.items(), key=lambda x: (x[1][0], x[0])):
        try:
            entry = _normalize_entry(provider(), default_order=int(order))
        except Exception:
            entry = None
        if entry is not None:
            out.append(entry)
    return out


def _chunks(items: Iterable[int], size: int = 400) -> Iterable[list[int]]:
    buf: list[int] = []
    for x in items:
        buf.append(int(x))
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf


def count_unsuspended_cards(cids: set[int]) -> int:
    if not cids or mw is None or not getattr(mw, "col", None):
        return 0
    total = 0
    for chunk in _chunks(cids, 400):
        qmarks = ",".join(["?"] * len(chunk))
        try:
            rows = mw.col.db.all(
                f"select queue from cards where id in ({qmarks})",
                *chunk,
            )
        except Exception:
            continue
        total += sum(1 for (q,) in rows if int(q) != -1)
    return int(total)

