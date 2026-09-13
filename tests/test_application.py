from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from talos.application import (
    ApplicationGenerateConfig,
    allocate_application_id,
    parse_application_markdown,
    parse_llm_json,
    run_generate_application,
    validate_record,
)
from talos.cli import cli
from talos.constants import APPLICATION_TYPES, WATERMARK
from talos.env import repo_root
from talos.errors import TalosError
from talos.generate import first_visible_line
from tests.fakes import FakeBlobStore
from tests.helpers import load_application_fixtures

pytestmark = pytest.mark.unit

FACTS = repo_root() / "corpus/facts.yaml"
FIXTURES = repo_root() / "tests/fixtures/client-applications"


class ScriptedCompleter:
    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = list(payloads)
        self.calls: list[list[dict[str, str]]] = []

    def complete(self, *, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        if not self.payloads:
            raise AssertionError("unexpected LLM call")
        payload = self.payloads.pop(0)
        return json.dumps(payload)


def _valid_record(kind: str, **overrides: object) -> dict:
    token = {
        "accepted": "ACCEPTED",
        "rejected": "REJECTED",
        "missing-data": "MISSING-DATA",
    }[kind]
    record: dict = {
        "application_id": f"CA-{token}-2026-01",
        "application_type": kind,
        "expected_judgement": kind,
        "expected_policy_ids": ["CP-RML-2026-01"],
        "customer_name": f"Pat {kind.title()}",
        "customer_id": "SYN-111111"
        if kind == "accepted"
        else ("SYN-222222" if kind == "rejected" else "SYN-333333"),
        "email": f"{kind.replace('-', '.')}@example.invalid",
        "phone": "+1-555-0100",
        "address": "1 Demo Street, Contoso City, CD 00000",
        "age_band": "35-44",
        "employer": "Northwind",
        "annual_income": "USD 90,000",
        "product": "owner-occupied residential mortgage",
        "facility": {"loan_amount": "USD 200,000", "credit_score": "720", "ltv": "70%"},
        "narrative": "Synthetic demo narrative for unit tests with enough length.",
        "missing_items": ["2 years tax returns"] if kind == "missing-data" else [],
    }
    record.update(overrides)
    return record


def _config(out: Path, **overrides: object) -> ApplicationGenerateConfig:
    values: dict[str, object] = dict(
        out=out,
        facts_path=FACTS,
        types=("accepted",),
        local_only=True,
        use_terraform=False,
        project_endpoint="https://example.services.ai.azure.com/api/projects/demo",
    )
    values.update(overrides)
    return ApplicationGenerateConfig(**values)  # type: ignore[arg-type]


def test_application_help_documents_flags() -> None:
    result = CliRunner().invoke(cli, ["generate", "application", "--help"])
    assert result.exit_code == 0
    for flag in ("--type", "--all", "--force", "--local-only", "--dry-run"):
        assert flag in result.output
    assert "knowledge source" in result.output.lower() or "PUT" in result.output


def test_application_requires_type_or_all() -> None:
    result = CliRunner().invoke(
        cli, ["generate", "application", "--local-only", "--no-terraform"]
    )
    assert result.exit_code == 1
    assert "--type" in result.output and "--all" in result.output


def test_application_dry_run_does_not_call_llm_or_write(tmp_path: Path) -> None:
    out = tmp_path / "apps"
    completer = ScriptedCompleter([_valid_record("accepted")])
    rendered = run_generate_application(
        _config(out, dry_run=True),
        completer=completer,
        echo=lambda _: None,
    )
    assert rendered == []
    assert completer.calls == []
    assert not out.exists()


def test_application_cli_dry_run_exit_0(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "generate",
            "application",
            "--type",
            "accepted",
            "--dry-run",
            "--local-only",
            "--out",
            str(tmp_path / "apps"),
            "--no-terraform",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "dry-run" in result.output
    assert "no LLM call" in result.output


def test_generate_one_slot_writes_watermarked_markdown(tmp_path: Path) -> None:
    out = tmp_path / "apps"
    completer = ScriptedCompleter([_valid_record("accepted")])
    rendered = run_generate_application(
        _config(out), completer=completer, echo=lambda _: None
    )
    assert len(rendered) == 1
    path = out / "accepted.md"
    text = path.read_text(encoding="utf-8")
    assert first_visible_line(text) == WATERMARK
    parsed = parse_application_markdown(text)
    assert parsed["application_id"] == "CA-ACCEPTED-2026-01"
    assert parsed["customer_id"] == "SYN-111111"
    assert parsed["email"].endswith("@example.invalid")
    assert parsed["facility"]["loan_amount"] == "USD 200,000"
    assert parsed["narrative"]
    assert (
        validate_record(
            parsed,
            application_type="accepted",
            used=set(),
            required_id="CA-ACCEPTED-2026-01",
        )
        == []
    )
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["container"] == "client-applications"
    assert manifest["documents"][0]["application_type"] == "accepted"


def test_generate_all_writes_three_unique_identities(tmp_path: Path) -> None:
    out = tmp_path / "apps"
    completer = ScriptedCompleter(
        [
            _valid_record("accepted"),
            _valid_record("rejected"),
            _valid_record("missing-data", expected_policy_ids=["CP-DOC-2026-01"]),
        ]
    )
    rendered = run_generate_application(
        _config(out, types=APPLICATION_TYPES),
        completer=completer,
        echo=lambda _: None,
    )
    assert len(rendered) == 3
    names = {item.record["customer_name"] for item in rendered}
    ids = {item.record["customer_id"] for item in rendered}
    assert len(names) == 3
    assert len(ids) == 3
    for kind in APPLICATION_TYPES:
        assert (out / f"{kind}.md").is_file()


def test_existing_slot_requires_force(tmp_path: Path) -> None:
    out = tmp_path / "apps"
    completer = ScriptedCompleter([_valid_record("accepted")])
    run_generate_application(_config(out), completer=completer, echo=lambda _: None)
    with pytest.raises(TalosError, match="pass --force"):
        run_generate_application(
            _config(out),
            completer=ScriptedCompleter([_valid_record("accepted")]),
            echo=lambda _: None,
        )
    run_generate_application(
        _config(out, force=True),
        completer=ScriptedCompleter(
            [
                _valid_record(
                    "accepted", customer_name="New Person", customer_id="SYN-444444"
                )
            ]
        ),
        echo=lambda _: None,
    )
    text = (out / "accepted.md").read_text(encoding="utf-8")
    assert "New Person" in text


def test_validation_retry_then_success(tmp_path: Path) -> None:
    bad = _valid_record("accepted", email="not-an-invalid-domain@example.com")
    good = _valid_record("accepted")
    completer = ScriptedCompleter([bad, good])
    rendered = run_generate_application(
        _config(tmp_path / "apps"), completer=completer, echo=lambda _: None
    )
    assert len(rendered) == 1
    assert len(completer.calls) == 2


def test_validation_failure_after_retry_writes_nothing(tmp_path: Path) -> None:
    bad = _valid_record("accepted", email="x@gmail.com")
    out = tmp_path / "apps"
    with pytest.raises(TalosError, match="after retry"):
        run_generate_application(
            _config(out),
            completer=ScriptedCompleter([bad, bad]),
            echo=lambda _: None,
        )
    assert not out.exists()


def test_missing_project_endpoint_exits_2(
    tmp_path: Path, clean_azure_env: None
) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "generate",
            "application",
            "--type",
            "accepted",
            "--local-only",
            "--out",
            str(tmp_path / "apps"),
            "--no-terraform",
        ],
    )
    assert result.exit_code == 2
    assert "AZURE_AI_PROJECT_ENDPOINT" in result.output


def test_optional_blob_upload_hash_metadata(tmp_path: Path) -> None:
    store = FakeBlobStore(container="client-applications")
    completer = ScriptedCompleter([_valid_record("accepted")])
    rendered = run_generate_application(
        _config(tmp_path / "apps", local_only=False),
        completer=completer,
        blob_store=store,
        echo=lambda _: None,
    )
    assert store.uploads == ["accepted.md"]
    blob = store.blobs["accepted.md"]
    assert blob.metadata["content_sha256"] == rendered[0].content_sha256
    assert blob.metadata["application_id"] == "CA-ACCEPTED-2026-01"
    assert blob.metadata["synthetic"] == "true"


def test_generate_application_does_not_put_knowledge_source(tmp_path: Path) -> None:
    source = (repo_root() / "src/talos/application.py").read_text(encoding="utf-8")
    assert "knowledgesources" not in source
    assert "ks-client-applications" not in source


def test_fixtures_parse_and_cover_each_type() -> None:
    fixtures = load_application_fixtures()
    kinds = {item["application_type"] for item in fixtures}
    assert kinds == set(APPLICATION_TYPES)
    for record in fixtures:
        path = FIXTURES / f"{record['application_type']}.md"
        text = path.read_text(encoding="utf-8")
        assert first_visible_line(text) == WATERMARK
        errors = validate_record(
            record,
            application_type=str(record["application_type"]),
            used=set(),
            required_id=str(record["application_id"]),
        )
        assert errors == [], errors


def test_gitignore_covers_generated_applications(repo_root: Path) -> None:
    nested = (repo_root / "data/client-applications/.gitignore").read_text(
        encoding="utf-8"
    )
    assert "*.md" in nested
    assert "manifest.json" in nested


def test_allocate_application_id_skips_used() -> None:
    used = {"CA-ACCEPTED-2026-01"}
    assert allocate_application_id("accepted", used) == "CA-ACCEPTED-2026-02"


def test_parse_llm_json_strips_fence() -> None:
    data = parse_llm_json('```json\n{"a": 1}\n```')
    assert data == {"a": 1}
