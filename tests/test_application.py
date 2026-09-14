from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from talos.application import (
    ApplicationGenerateConfig,
    allocate_application_id,
    application_filename,
    attached_documents_for,
    contains_forbidden_outcome_token,
    credit_application_heading,
    parse_application_markdown,
    parse_llm_json,
    run_generate_application,
    validate_record,
)
from talos.cli import cli
from talos.constants import (
    APPLICATION_ID_RE,
    APPLICATION_TYPES,
    FORBIDDEN_OUTCOME_TOKENS,
    PRODUCT_FAMILIES,
    PRODUCT_FAMILY_LABEL,
    PRODUCT_REQUIRED_DOCUMENTS,
    SLOT_PRODUCT_FAMILY,
    WATERMARK,
)
from talos.env import repo_root
from talos.errors import TalosError
from talos.generate import first_visible_line
from tests.fakes import FakeBlob, FakeBlobStore
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
    family = SLOT_PRODUCT_FAMILY[kind]
    attached, _omitted = attached_documents_for(kind, family)
    names = {
        "accepted": ("Pat Rivet", "SYN-111111", "pat.rivet@example.invalid"),
        "rejected": ("Pat Quarry", "SYN-222222", "pat.quarry@example.invalid"),
        "missing-data": ("Pat Harbor", "SYN-333333", "pat.harbor@example.invalid"),
    }
    customer_name, customer_id, email = names[kind]
    record: dict = {
        "application_id": "CA-2026-000001",
        "customer_name": customer_name,
        "customer_id": customer_id,
        "email": email,
        "phone": "+1-555-0100",
        "address": "1 Demo Street, Contoso City, CD 00000",
        "age_band": "35-44",
        "employer": "Northwind",
        "annual_income": "USD 90,000",
        "product": PRODUCT_FAMILY_LABEL[family],
        "product_family": family,
        "facility": {
            "accepted": {
                "loan_amount": "USD 320,000",
                "property_value": "USD 450,000",
                "ltv": "71%",
                "dti": "36%",
                "credit_score": "720",
                "occupancy": "owner-occupied",
            },
            "rejected": {
                "loan_amount": "USD 3,600,000",
                "property_value": "USD 5,000,000",
                "ltv": "72%",
                "dscr": "1.10x",
            },
            "missing-data": {
                "loan_amount": "USD 400,000",
                "years_in_operation": "5 years",
                "tenor_months": "12",
            },
        }[kind],
        "narrative": "I request this synthetic demo facility and list the documents I am submitting.",
        "attached_documents": list(attached),
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
    assert "operator" in result.output.lower()


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
    assert "credit-application-CA-" in result.output


def test_generate_one_slot_writes_opaque_customer_filing(tmp_path: Path) -> None:
    out = tmp_path / "apps"
    completer = ScriptedCompleter([_valid_record("accepted")])
    rendered = run_generate_application(
        _config(out), completer=completer, echo=lambda _: None
    )
    assert len(rendered) == 1
    application_id = rendered[0].record["application_id"]
    assert re.fullmatch(APPLICATION_ID_RE, application_id)
    assert not contains_forbidden_outcome_token(application_id)
    filename = application_filename(application_id)
    assert filename == f"credit-application-{application_id}.md"
    path = out / filename
    text = path.read_text(encoding="utf-8")
    assert first_visible_line(text) == credit_application_heading(application_id)
    assert not text.lstrip().startswith(WATERMARK)
    assert not text.lstrip().startswith("---")
    parsed = parse_application_markdown(text)
    assert parsed["application_id"] == application_id
    assert parsed["customer_id"] == "SYN-111111"
    assert parsed["email"].endswith("@example.invalid")
    assert parsed["facility"]["loan_amount"] == "USD 320,000"
    assert parsed["narrative"]
    assert "identity" in text.lower()
    assert "product" in text.lower()
    assert "attached document" in text.lower()
    assert parsed["facility"]["loan_amount"] in text
    for title in parsed["attached_documents"]:
        assert title in text
    assert "application_type" not in parsed
    assert "intended_outcome" not in parsed
    assert "expected_judgement" not in text
    assert "application_type" not in text
    assert "intended_outcome" not in text
    assert "missing-data" not in text
    assert (
        validate_record(
            parsed,
            application_type="accepted",
            used=set(),
            required_id=application_id,
            product_family=SLOT_PRODUCT_FAMILY["accepted"],
        )
        == []
    )
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["container"] == "client-applications"
    assert manifest["documents"][0]["intended_outcome"] == "accepted"
    assert manifest["documents"][0]["slot"] == "accepted"
    assert manifest["documents"][0]["filename"] == filename
    assert not (out / "accepted.md").exists()
    extras = [p for p in out.iterdir() if p.suffix not in {".md", ".json"}]
    assert extras == []


def test_generate_all_writes_three_unique_identities_and_products(
    tmp_path: Path,
) -> None:
    out = tmp_path / "apps"
    completer = ScriptedCompleter(
        [
            _valid_record("accepted"),
            _valid_record("rejected"),
            _valid_record("missing-data"),
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
    app_ids = {item.record["application_id"] for item in rendered}
    families = {item.record["product_family"] for item in rendered}
    assert len(names) == 3
    assert len(ids) == 3
    assert len(app_ids) == 3
    assert len(families) == 3
    assert families <= set(PRODUCT_FAMILIES)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    slots = {doc["slot"] for doc in manifest["documents"]}
    assert slots == set(APPLICATION_TYPES)
    for doc in manifest["documents"]:
        assert re.fullmatch(APPLICATION_ID_RE, doc["application_id"])
        assert not contains_forbidden_outcome_token(doc["application_id"])
        assert doc["filename"] == f"credit-application-{doc['application_id']}.md"
        assert (out / doc["filename"]).is_file()
        assert doc["intended_outcome"] == doc["slot"]
        text = (out / doc["filename"]).read_text(encoding="utf-8")
        assert "intended_outcome" not in text
        assert "application_type" not in text
        assert "missing-data" not in text
        assert "--type" not in text
        assert doc["intended_outcome"] not in text


def test_attached_docs_complete_or_omitted_by_slot(tmp_path: Path) -> None:
    out = tmp_path / "apps"
    completer = ScriptedCompleter(
        [
            _valid_record("accepted"),
            _valid_record("rejected"),
            _valid_record("missing-data"),
        ]
    )
    rendered = run_generate_application(
        _config(out, types=APPLICATION_TYPES),
        completer=completer,
        echo=lambda _: None,
    )
    by_slot = {item.application_type: item for item in rendered}
    for kind in ("accepted", "rejected"):
        family = by_slot[kind].record["product_family"]
        attached = {
            title.strip() for title in by_slot[kind].record["attached_documents"]
        }
        assert attached == set(PRODUCT_REQUIRED_DOCUMENTS[family])
    missing = by_slot["missing-data"]
    family = missing.record["product_family"]
    attached = {title.strip() for title in missing.record["attached_documents"]}
    required = set(PRODUCT_REQUIRED_DOCUMENTS[family])
    assert attached < required
    assert required - attached


def test_existing_slot_requires_force(tmp_path: Path) -> None:
    out = tmp_path / "apps"
    completer = ScriptedCompleter([_valid_record("accepted")])
    first = run_generate_application(
        _config(out), completer=completer, echo=lambda _: None
    )
    old_name = first[0].filename
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
    text = (out / old_name).read_text(encoding="utf-8")
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


def test_force_overwrite_deletes_previous_application_blob(tmp_path: Path) -> None:
    out = tmp_path / "apps"
    out.mkdir()
    old_name = "credit-application-CA-2025-000099.md"
    (out / old_name).write_text(
        "# Credit application CA-2025-000099\n", encoding="utf-8"
    )
    (out / "manifest.json").write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "slot": "accepted",
                        "application_id": "CA-2025-000099",
                        "intended_outcome": "accepted",
                        "filename": old_name,
                        "customer_name": "Old Person",
                        "customer_id": "SYN-000001",
                        "product_family": "residential_mortgage",
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    store = FakeBlobStore(container="client-applications")
    store.blobs[old_name] = FakeBlob(data=b"old", metadata={})
    store.blobs["accepted.md"] = FakeBlob(data=b"legacy", metadata={})
    rendered = run_generate_application(
        _config(out, local_only=False, force=True),
        completer=ScriptedCompleter([_valid_record("accepted")]),
        blob_store=store,
        echo=lambda _: None,
    )
    new_name = rendered[0].filename
    assert new_name != old_name
    assert old_name not in store.blobs
    assert "accepted.md" not in store.blobs
    assert new_name in store.blobs
    assert not (out / old_name).exists()
    assert not (out / "accepted.md").exists()


def test_orphan_local_application_files_are_removed(tmp_path: Path) -> None:
    out = tmp_path / "apps"
    out.mkdir()
    (out / "credit-application-CA-2025-000050.md").write_text(
        "orphan\n", encoding="utf-8"
    )
    rendered = run_generate_application(
        _config(out),
        completer=ScriptedCompleter([_valid_record("accepted")]),
        echo=lambda _: None,
    )
    assert not (out / "credit-application-CA-2025-000050.md").exists()
    assert (out / rendered[0].filename).is_file()


def test_corrupt_manifest_fails(tmp_path: Path) -> None:
    out = tmp_path / "apps"
    out.mkdir()
    (out / "manifest.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(TalosError, match="invalid application manifest"):
        run_generate_application(
            _config(out),
            completer=ScriptedCompleter([_valid_record("accepted")]),
            echo=lambda _: None,
        )


def test_optional_blob_upload_hash_metadata(tmp_path: Path) -> None:
    store = FakeBlobStore(container="client-applications")
    completer = ScriptedCompleter([_valid_record("accepted")])
    rendered = run_generate_application(
        _config(tmp_path / "apps", local_only=False),
        completer=completer,
        blob_store=store,
        echo=lambda _: None,
    )
    filename = rendered[0].filename
    assert store.uploads == [filename]
    blob = store.blobs[filename]
    assert blob.metadata["content_sha256"] == rendered[0].content_sha256
    assert blob.metadata["application_id"] == rendered[0].record["application_id"]
    assert blob.metadata["synthetic"] == "true"
    assert "application_type" not in blob.metadata


def test_generate_application_does_not_put_knowledge_source(tmp_path: Path) -> None:
    source = (repo_root() / "src/talos/application.py").read_text(encoding="utf-8")
    assert "knowledgesources" not in source
    assert "ks-client-applications" not in source


def test_fixtures_parse_and_cover_each_type() -> None:
    fixtures = load_application_fixtures()
    kinds = {item["application_type"] for item in fixtures}
    assert kinds == set(APPLICATION_TYPES)
    families = {item["product_family"] for item in fixtures}
    assert len(families) == 3
    for record in fixtures:
        filename = str(record["filename"])
        path = FIXTURES / filename
        text = path.read_text(encoding="utf-8")
        assert first_visible_line(text) == credit_application_heading(
            str(record["application_id"])
        )
        assert not text.lstrip().startswith(WATERMARK)
        assert not text.lstrip().startswith("---")
        assert filename == f"credit-application-{record['application_id']}.md"
        assert re.fullmatch(APPLICATION_ID_RE, str(record["application_id"]))
        assert not contains_forbidden_outcome_token(str(record["application_id"]))
        assert "intended_outcome" not in text
        assert "application_type" not in text
        assert "expected_judgement" not in text
        parsed = parse_application_markdown(text)
        errors = validate_record(
            parsed,
            application_type=str(record["application_type"]),
            used=set(),
            required_id=str(record["application_id"]),
            product_family=str(record["product_family"]),
        )
        assert errors == [], errors
        family = str(record["product_family"])
        attached = {title.strip() for title in parsed["attached_documents"]}
        required = set(PRODUCT_REQUIRED_DOCUMENTS[family])
        if record["application_type"] == "missing-data":
            assert attached < required
        else:
            assert attached == required


def test_gitignore_covers_generated_applications(repo_root: Path) -> None:
    nested = (repo_root / "data/client-applications/.gitignore").read_text(
        encoding="utf-8"
    )
    assert "*.md" in nested
    assert "manifest.json" in nested


def test_allocate_application_id_skips_used() -> None:
    used = {"CA-2026-000001"}
    assert allocate_application_id(used, year=2026) == "CA-2026-000002"
    assert re.fullmatch(APPLICATION_ID_RE, allocate_application_id(set(), year=2026))


def test_forbidden_outcome_tokens_are_rejected_in_id() -> None:
    for token in FORBIDDEN_OUTCOME_TOKENS:
        assert contains_forbidden_outcome_token(f"CA-{token}-2026-01")


def test_required_doc_titles_appear_in_published_policies(repo_root: Path) -> None:
    corpus = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (repo_root / "data/credit-policies").glob("*.md")
    ).lower()
    for titles in PRODUCT_REQUIRED_DOCUMENTS.values():
        for title in titles:
            assert title.lower() in corpus, title


def test_validate_record_rejects_judgement_tokens_in_narrative() -> None:
    record = _valid_record("accepted", narrative="Please treat this as accepted.")
    errors = validate_record(
        record,
        application_type="accepted",
        used=set(),
        required_id=record["application_id"],
        product_family="residential_mortgage",
    )
    assert any("judgement" in err or "ApplicationType" in err for err in errors)


def test_validate_record_rejects_judgement_tokens_in_email() -> None:
    record = _valid_record("accepted", email="accepted.case@example.invalid")
    errors = validate_record(
        record,
        application_type="accepted",
        used=set(),
        required_id=record["application_id"],
        product_family="residential_mortgage",
    )
    assert any("judgement" in err or "ApplicationType" in err for err in errors)


def test_validate_record_pins_product_label() -> None:
    record = _valid_record("accepted", product="some other mortgage product")
    errors = validate_record(
        record,
        application_type="accepted",
        used=set(),
        required_id=record["application_id"],
        product_family="residential_mortgage",
    )
    assert any("product must be" in err for err in errors)


def test_validate_record_checks_facility_limits() -> None:
    too_high = _valid_record("accepted")
    too_high["facility"] = dict(too_high["facility"], ltv="85%")
    errors = validate_record(
        too_high,
        application_type="accepted",
        used=set(),
        required_id=too_high["application_id"],
        product_family="residential_mortgage",
    )
    assert any("clear published limits" in err for err in errors)
    inside = _valid_record("rejected")
    inside["facility"] = dict(inside["facility"], ltv="60%", dscr="1.40x")
    errors = validate_record(
        inside,
        application_type="rejected",
        used=set(),
        required_id=inside["application_id"],
        product_family="commercial_real_estate",
    )
    assert any("breach at least one" in err for err in errors)


def test_parse_llm_json_strips_fence() -> None:
    data = parse_llm_json('```json\n{"a": 1}\n```')
    assert data == {"a": 1}


def test_generated_markdown_opens_with_heading_not_watermark(tmp_path: Path) -> None:
    out = tmp_path / "apps"
    rendered = run_generate_application(
        _config(out),
        completer=ScriptedCompleter([_valid_record("accepted")]),
        echo=lambda _: None,
    )
    text = (out / rendered[0].filename).read_text(encoding="utf-8")
    heading = credit_application_heading(rendered[0].record["application_id"])
    assert first_visible_line(text) == heading
    assert text.startswith(heading)
    assert WATERMARK not in text.splitlines()[0]


def test_generated_markdown_has_no_yaml_frontmatter(tmp_path: Path) -> None:
    out = tmp_path / "apps"
    rendered = run_generate_application(
        _config(out),
        completer=ScriptedCompleter([_valid_record("accepted")]),
        echo=lambda _: None,
    )
    text = (out / rendered[0].filename).read_text(encoding="utf-8")
    before_heading: list[str] = []
    for line in text.splitlines():
        if line.startswith("# Credit application "):
            break
        before_heading.append(line.strip())
    assert "---" not in before_heading
    with pytest.raises(TalosError, match="YAML front matter"):
        parse_application_markdown(
            "---\napplication_id: CA-2026-000001\n---\n"
            "# Credit application CA-2026-000001\n"
        )


def test_parse_rejects_watermark_prefix() -> None:
    with pytest.raises(TalosError, match="must not start with the policy watermark"):
        parse_application_markdown(
            f"{WATERMARK}\n\n# Credit application CA-2026-000001\n"
        )
