from __future__ import annotations

from typing import Any

from . import browser_graph


def build_dep_tree_raw(current_nid: int) -> tuple[set[int], list[tuple[int, int]], dict[int, str]]:
    return browser_graph._family_prio_chain(int(current_nid))  # noqa: SLF001 - shared package internals


def build_dep_tree_payload(
    current_nid: int,
    nodes: set[int],
    edges: list[tuple[int, int]],
    labels: dict[int, str],
) -> dict[str, Any]:
    return browser_graph._build_prio_chain_payload(  # noqa: SLF001 - shared package internals
        int(current_nid), nodes, edges, labels
    )


def estimate_dep_tree_height(
    current_nid: int,
    nodes: set[int],
    edges: list[tuple[int, int]],
    labels: dict[int, str],
    view_width: int,
) -> int:
    return int(
        browser_graph._estimate_prio_needed_height(  # noqa: SLF001 - shared package internals
            int(current_nid), nodes, edges, labels, int(view_width)
        )
    )

