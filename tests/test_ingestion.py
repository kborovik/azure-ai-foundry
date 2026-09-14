from __future__ import annotations

from typing import Any

import pytest

from talos.constants import (
    DEFAULT_APPLICATION_KNOWLEDGE_SOURCE,
    DEFAULT_APPLICATION_OUTPUT_RELATIVE,
    DEFAULT_KNOWLEDGE_SOURCE,
    MIN_INDEXED_ITEMS,
    SEARCH_SCOPE,
)
from talos.env import repo_root
from talos.provision import (
    extract_index_name,
    local_corpus_size,
    synchronization_counts,
)
from tests.live_support import get_or_skip, knowledge_source_status, search_url

pytestmark = pytest.mark.ingestion


def _index_count(live_rest: Any, live_env: dict[str, str], ks_name: str) -> int:
    ks = get_or_skip(
        live_rest,
        search_url(live_env, f"knowledgesources/{ks_name}"),
        scope=SEARCH_SCOPE,
        action=f"GET knowledge source {ks_name}",
    )
    index_name = extract_index_name(ks)
    if not index_name:
        pytest.skip(f"{ks_name} has no createdResources.index")
    response = live_rest.request(
        "GET",
        search_url(live_env, f"indexes/{index_name}/docs/$count"),
        scope=SEARCH_SCOPE,
    )
    if isinstance(response.json, int):
        return response.json
    text = (response.text or "").strip()
    return int(text) if text.isdigit() else 0


def test_policy_knowledge_source_indexed(
    live_env: dict[str, str], live_rest: Any
) -> None:
    status = knowledge_source_status(live_rest, live_env, DEFAULT_KNOWLEDGE_SOURCE)
    end_time, processed, failed = synchronization_counts(status)
    if end_time is None:
        pytest.skip("policy knowledge source has not finished indexing")
    assert failed == 0
    counted = (
        processed
        if processed >= MIN_INDEXED_ITEMS
        else _index_count(live_rest, live_env, DEFAULT_KNOWLEDGE_SOURCE)
    )
    assert counted >= MIN_INDEXED_ITEMS


def test_application_knowledge_source_indexed(
    live_env: dict[str, str], live_rest: Any
) -> None:
    status = knowledge_source_status(
        live_rest, live_env, DEFAULT_APPLICATION_KNOWLEDGE_SOURCE
    )
    end_time, processed, failed = synchronization_counts(status)
    if end_time is None:
        pytest.skip("application knowledge source has not finished indexing")
    assert failed == 0
    expected = local_corpus_size(repo_root() / DEFAULT_APPLICATION_OUTPUT_RELATIVE)
    if expected == 0:
        pytest.skip("no local application corpus")
    counted = (
        processed
        if processed >= expected
        else _index_count(live_rest, live_env, DEFAULT_APPLICATION_KNOWLEDGE_SOURCE)
    )
    assert counted >= expected
