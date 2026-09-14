from __future__ import annotations

import pytest

from talos.constants import DEFAULT_INSTRUCTIONS_RELATIVE, REFUSAL_SENTENCE, WATERMARK
from talos.env import repo_root

pytestmark = pytest.mark.unit


def test_instructions_contain_evaluation_mode() -> None:
    text = (repo_root() / DEFAULT_INSTRUCTIONS_RELATIVE).read_text(encoding="utf-8")
    upper = text.upper()
    assert "EVALUATION MODE" in upper or "EVALUATIONMODE" in upper.replace(" ", "")
    assert "application_id" in text
    assert "customer_name" in text
    assert "ask" in text.lower()
    assert "missing" in text.lower()
    assert "accept" in text.lower() and "reject" in text.lower()
    assert "missing-data" in text
    assert "ks-client-applications" in text
    assert "ks-credit-policies" in text
    assert "【message_idx:search_idx†source_name】" in text
    assert "never cite an application blob" in text.lower() or (
        "never cite" in text.lower() and "application blob" in text.lower()
    )
    assert (
        REFUSAL_SENTENCE in text.lower()
        or "That is not in the published policies." in text
    )
    assert WATERMARK.split("—")[0].strip() in text or "SYNTHETIC" in text
    assert "type nicknames" in text.lower() or "`accepted`" in text
    assert "CA-{YYYYMMDD}-{unix_ms}" in text
    assert "CP-DOC-2026-01" in text
    assert "attached" in text.lower()
    assert "required-document" in text.lower() or "required document" in text.lower()
    assert "infer" in text.lower()
    assert "filename" in text.lower()
    assert "source_name" in text
    assert "judgement" in text.lower()
    assert "emit" in text.lower() or "output a judgement" in text.lower()
