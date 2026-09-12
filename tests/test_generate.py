from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from talos.cli import cli
from talos.constants import CORPUS_IDS, WATERMARK
from talos.env import repo_root
from talos.generate import first_visible_line, load_and_validate_facts
from talos.errors import TalosError

pytestmark = pytest.mark.unit

FACTS = repo_root() / "corpus/facts.yaml"
TEMPLATES = repo_root() / "corpus/templates"


def _generate_args(out: Path, *extra: str) -> list[str]:
    return [
        "generate",
        "--local-only",
        "--out",
        str(out),
        "--facts",
        str(FACTS),
        "--templates",
        str(TEMPLATES),
        "--no-azd",
        *extra,
    ]


def test_generate_help_documents_flags() -> None:
    result = CliRunner().invoke(cli, ["generate", "--help"])
    assert result.exit_code == 0
    for flag in (
        "--out",
        "--facts",
        "--templates",
        "--local-only",
        "--azure-only",
        "--dry-run",
        "--force",
        "--fail-if-missing-azure",
        "--no-azd",
    ):
        assert flag in result.output


def test_generate_local_only_writes_twelve_markdown_and_manifest(
    tmp_path: Path,
) -> None:
    out = tmp_path / "credit-policies"
    result = CliRunner().invoke(cli, _generate_args(out))
    assert result.exit_code == 0, result.output
    documents = yaml.safe_load(FACTS.read_text(encoding="utf-8"))["documents"]
    assert len(documents) == 12
    for doc in documents:
        path = out / doc["filename"]
        assert path.is_file(), path
        assert path.read_text(encoding="utf-8").strip()
    manifest = yaml.safe_load((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["watermark"] == WATERMARK
    assert manifest["container"] == "credit-policies"
    assert {item["id"] for item in manifest["documents"]} == set(CORPUS_IDS)
    assert len(manifest["documents"]) == 12


def test_watermark_is_first_visible_line(tmp_path: Path) -> None:
    out = tmp_path / "credit-policies"
    result = CliRunner().invoke(cli, _generate_args(out))
    assert result.exit_code == 0, result.output
    for path in out.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert first_visible_line(text) == WATERMARK


def test_fact_keys_are_unique_and_values_appear_verbatim(tmp_path: Path) -> None:
    documents = load_and_validate_facts(FACTS)
    keys = [key for doc in documents for key in doc.facts]
    assert len(keys) == len(set(keys))
    out = tmp_path / "credit-policies"
    result = CliRunner().invoke(cli, _generate_args(out))
    assert result.exit_code == 0, result.output
    for doc in documents:
        text = (out / doc.filename).read_text(encoding="utf-8")
        for value in doc.facts.values():
            assert value in text, f"{doc.id} missing {value!r}"


def test_threshold_sentences_use_fact_literals(tmp_path: Path) -> None:
    out = tmp_path / "credit-policies"
    result = CliRunner().invoke(cli, _generate_args(out))
    assert result.exit_code == 0, result.output
    rml = (out / "CP-RML-2026-01-residential-mortgage.md").read_text(encoding="utf-8")
    ucl = (out / "CP-UCL-2026-01-unsecured-consumer.md").read_text(encoding="utf-8")
    exc = (out / "CP-EXC-2026-01-exceptions-overrides.md").read_text(encoding="utf-8")
    assert "80%" in rml
    assert "eighty percent" not in rml.lower()
    assert "USD 50,000" in ucl
    assert "$50,000" not in ucl
    assert "Credit Exceptions Committee" in rml
    assert "Credit Exceptions Committee" in exc


def test_duplicate_fact_key_exits_3(tmp_path: Path) -> None:
    data = yaml.safe_load(FACTS.read_text(encoding="utf-8"))
    data["documents"][1]["facts"]["max_ltv_owner_occupied"] = "99%"
    facts_path = tmp_path / "facts.yaml"
    facts_path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    out = tmp_path / "out"
    result = CliRunner().invoke(
        cli,
        [
            "generate",
            "--local-only",
            "--out",
            str(out),
            "--facts",
            str(facts_path),
            "--templates",
            str(TEMPLATES),
            "--no-azd",
        ],
    )
    assert result.exit_code == 3, result.output
    assert "duplicate fact key" in result.output
    assert not out.exists()


def test_invalid_yaml_exits_3(tmp_path: Path) -> None:
    facts_path = tmp_path / "facts.yaml"
    facts_path.write_text("{ not: valid: yaml", encoding="utf-8")
    result = CliRunner().invoke(
        cli,
        [
            "generate",
            "--local-only",
            "--out",
            str(tmp_path / "out"),
            "--facts",
            str(facts_path),
            "--templates",
            str(TEMPLATES),
            "--no-azd",
        ],
    )
    assert result.exit_code == 3, result.output


def test_local_and_azure_only_are_mutex() -> None:
    result = CliRunner().invoke(
        cli, ["generate", "--local-only", "--azure-only", "--no-azd"]
    )
    assert result.exit_code == 1, result.output
    assert "mutually exclusive" in result.output


def test_fail_if_missing_azure_exits_2(clean_azure_env: None) -> None:
    result = CliRunner().invoke(
        cli, ["generate", "--fail-if-missing-azure", "--no-azd"]
    )
    assert result.exit_code == 2, result.output
    assert "Azure environment is not configured" in result.output


def test_azure_only_missing_env_exits_2(clean_azure_env: None) -> None:
    result = CliRunner().invoke(cli, ["generate", "--azure-only", "--no-azd"])
    assert result.exit_code == 2, result.output


def test_local_only_does_not_require_azure(
    tmp_path: Path, clean_azure_env: None
) -> None:
    result = CliRunner().invoke(
        cli, _generate_args(tmp_path / "out", "--fail-if-missing-azure")
    )
    assert result.exit_code == 0, result.output


def test_dry_run_does_not_write(tmp_path: Path) -> None:
    out = tmp_path / "credit-policies"
    result = CliRunner().invoke(cli, _generate_args(out, "--dry-run"))
    assert result.exit_code == 0, result.output
    assert "dry-run" in result.output
    assert not out.exists()


def test_load_and_validate_facts_rejects_wrong_watermark(tmp_path: Path) -> None:
    data = yaml.safe_load(FACTS.read_text(encoding="utf-8"))
    data["watermark"] = "DEMO"
    path = tmp_path / "facts.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(TalosError) as exc:
        load_and_validate_facts(path)
    assert exc.value.exit_code == 3
    assert "watermark" in str(exc.value)
