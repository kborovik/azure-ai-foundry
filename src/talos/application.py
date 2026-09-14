from __future__ import annotations

import hashlib
import json
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateError
from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential

from talos.constants import (
    APPLICATION_FILENAME_TEMPLATE,
    APPLICATION_ID_RE,
    APPLICATION_LLM_ATTEMPTS,
    APPLICATION_TYPES,
    CUSTOMER_ID_RE,
    DEFAULT_APPLICATION_CONTAINER,
    DEFAULT_APPLICATION_OUTPUT_RELATIVE,
    DEFAULT_APPLICATION_SCHEMA_RELATIVE,
    DEFAULT_APPLICATION_SYSTEM_PROMPT_RELATIVE,
    DEFAULT_APPLICATION_TEMPLATE_RELATIVE,
    DEFAULT_APPLICATION_USER_PROMPT_RELATIVE,
    DEFAULT_CHAT_DEPLOYMENT,
    EMAIL_DOMAIN,
    FACILITY_PROMPT_HINTS,
    FORBIDDEN_OUTCOME_TOKENS,
    FOUNDRY_SCOPE,
    PRODUCT_FACILITY_LIMITS,
    PRODUCT_FAMILIES,
    PRODUCT_FAMILY_LABEL,
    PRODUCT_REQUIRED_DOCUMENTS,
    SLOT_PRODUCT_FAMILY,
    WATERMARK,
)
from talos.env import (
    azure_generate_configured,
    repo_root,
    resolve_env,
    resolve_generate_env,
)
from talos.errors import TalosError
from talos.generate import BlobStore, first_visible_line, open_blob_store
from talos.rest import RestClient, raise_for_status

Echo = Callable[[str], None]

REQUIRED_JSON_KEYS = (
    "application_id",
    "customer_name",
    "customer_id",
    "email",
    "phone",
    "address",
    "age_band",
    "employer",
    "annual_income",
    "product",
    "facility",
    "narrative",
    "attached_documents",
)
REQUIRED_FACILITY_KEYS = ("loan_amount",)
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
NATIONAL_ID_RE = re.compile(r"\b\d{6}[- ]\d{4}\b")
CREDIT_APPLICATION_HEADING_RE = re.compile(r"^# Credit application (CA-\d{4}-\d{6})$")
IDENTITY_FIELD_BY_LABEL = {
    "name": "customer_name",
    "customer id": "customer_id",
    "address": "address",
    "age band": "age_band",
    "employer": "employer",
    "annual income": "annual_income",
    "email": "email",
    "phone": "phone",
}
JUDGEMENT_LEAK_RE = re.compile(
    r"application_type|intended_outcome|expected_judgement|missing_items|"
    r"\bmissing-data\b|\bapplicationtype\b|"
    r"\baccepted\b|\brejected\b|\bapproved\b|\bdeclined\b|\bdenied\b",
    re.I,
)
FACILITY_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)")
OPERATOR_RECORD_KEYS = (
    "application_type",
    "expected_judgement",
    "intended_outcome",
    "missing_items",
    "expected_policy_ids",
)


@dataclass(frozen=True)
class ApplicationGenerateConfig:
    out: Path
    facts_path: Path
    types: tuple[str, ...]
    force: bool = False
    local_only: bool = False
    dry_run: bool = False
    use_terraform: bool = True
    account_url: str = ""
    container: str = DEFAULT_APPLICATION_CONTAINER
    project_endpoint: str = ""
    chat_deployment: str = DEFAULT_CHAT_DEPLOYMENT
    schema_path: Path | None = None
    system_prompt_path: Path | None = None
    user_prompt_path: Path | None = None
    template_path: Path | None = None


@dataclass(frozen=True)
class RenderedApplication:
    application_type: str
    filename: str
    markdown: str
    content_sha256: str
    record: dict[str, Any]


class ChatCompleter(Protocol):
    def complete(self, *, messages: list[dict[str, str]]) -> str: ...


class FoundryChatCompleter:
    def __init__(
        self,
        rest: RestClient,
        project_endpoint: str,
        model: str = DEFAULT_CHAT_DEPLOYMENT,
    ) -> None:
        self._rest = rest
        self._project_endpoint = project_endpoint.rstrip("/")
        self._model = model

    def complete(self, *, messages: list[dict[str, str]]) -> str:
        url = f"{self._project_endpoint}/openai/v1/chat/completions"
        body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        try:
            response = self._rest.request(
                "POST",
                url,
                scope=FOUNDRY_SCOPE,
                json_body=body,
                timeout=120.0,
            )
            raise_for_status(response, "Foundry chat completions")
        except TalosError as exc:
            raise TalosError(f"LLM call failed: {exc}", exit_code=1) from exc
        payload = response.json if isinstance(response.json, dict) else {}
        choices = payload.get("choices") or []
        if not isinstance(choices, list) or not choices:
            raise TalosError("LLM call failed: empty choices", exit_code=1)
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise TalosError("LLM call failed: empty content", exit_code=1)
        return content


def application_filename(application_id: str) -> str:
    if not re.fullmatch(APPLICATION_ID_RE, application_id):
        raise TalosError(
            f"application_id {application_id!r} is not CA-YYYY-NNNNNN",
            exit_code=1,
        )
    return APPLICATION_FILENAME_TEMPLATE.format(application_id=application_id)


def contains_forbidden_outcome_token(value: str) -> bool:
    upper = value.upper()
    return any(token in upper for token in FORBIDDEN_OUTCOME_TOKENS)


def assign_product_family(slot: str, used_families: set[str]) -> str:
    preferred = SLOT_PRODUCT_FAMILY[slot]
    if preferred not in used_families:
        return preferred
    for family in PRODUCT_FAMILIES:
        if family not in used_families:
            return family
    return preferred


def attached_documents_for(
    application_type: str, product_family: str
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    required = PRODUCT_REQUIRED_DOCUMENTS[product_family]
    if application_type == "missing-data":
        return required[1:], (required[0],)
    return required, ()


def parse_facility_number(value: object) -> float | None:
    match = FACILITY_NUMBER_RE.search(str(value).replace(",", ""))
    if match is None:
        return None
    return float(match.group(1))


def facility_clears_limit(value: float, op: str, limit: float) -> bool:
    if op == "<=":
        return value <= limit
    if op == ">=":
        return value >= limit
    raise TalosError(f"unknown facility comparison {op!r}", exit_code=1)


def facility_limit_errors(
    facility: dict[str, Any],
    *,
    application_type: str,
    product_family: str,
) -> list[str]:
    checks = PRODUCT_FACILITY_LIMITS[product_family]
    evaluated: list[tuple[str, bool]] = []
    errors: list[str] = []
    required_fields = {field for field, _op, _limit in checks}
    if application_type in ("accepted", "rejected"):
        missing = [
            field for field in required_fields if facility.get(field) in (None, "")
        ]
        if missing:
            errors.append(
                f"facility missing {', '.join(sorted(missing))} for {product_family}"
            )
            return errors
    for field, op, limit in checks:
        raw = facility.get(field)
        if raw in (None, ""):
            continue
        number = parse_facility_number(raw)
        if number is None:
            errors.append(f"facility.{field} is not numeric: {raw!r}")
            continue
        evaluated.append((field, facility_clears_limit(number, op, limit)))
    if not evaluated:
        return errors
    clears = [ok for _field, ok in evaluated]
    if application_type == "accepted" and not all(clears):
        failed = [field for field, ok in evaluated if not ok]
        errors.append(f"accepted facility must clear published limits; failed {failed}")
    if application_type == "rejected" and all(clears):
        errors.append("rejected facility must breach at least one published limit")
    return errors


def parse_llm_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines)
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise TalosError(f"LLM JSON parse failed: {exc}", exit_code=1) from exc
    if not isinstance(data, dict):
        raise TalosError("LLM JSON root must be an object", exit_code=1)
    return data


def credit_application_heading(application_id: str) -> str:
    return f"# Credit application {application_id}"


def _yaml_prefix_present(text: str) -> bool:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# Credit application "):
            return False
        if stripped == "---":
            return True
    return False


def _markdown_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip().casefold()
            sections[current] = []
            continue
        if current is not None:
            sections[current].append(line)
    return {key: "\n".join(lines).strip() for key, lines in sections.items()}


def _parse_labeled_bullets(block: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- ") or ":" not in stripped:
            continue
        key, value = stripped[2:].split(":", 1)
        result[key.strip()] = value.strip()
    return result


def _parse_plain_bullets(block: str) -> list[str]:
    return [
        line.strip()[2:].strip()
        for line in block.splitlines()
        if line.strip().startswith("- ")
    ]


def parse_application_markdown(text: str) -> dict[str, Any]:
    first = first_visible_line(text)
    if first == WATERMARK:
        raise TalosError(
            "application markdown must not start with the policy watermark",
            exit_code=1,
        )
    if _yaml_prefix_present(text):
        raise TalosError(
            "application markdown must not include YAML front matter",
            exit_code=1,
        )
    heading = CREDIT_APPLICATION_HEADING_RE.fullmatch(first)
    if heading is None:
        raise TalosError(
            "first visible line must be '# Credit application CA-YYYY-NNNNNN', "
            f"got {first!r}",
            exit_code=1,
        )
    sections = _markdown_sections(text)
    identity_labels = _parse_labeled_bullets(sections.get("identity", ""))
    identity = {
        IDENTITY_FIELD_BY_LABEL[label.casefold()]: value
        for label, value in identity_labels.items()
        if label.casefold() in IDENTITY_FIELD_BY_LABEL
    }
    return {
        "application_id": heading.group(1),
        "customer_name": identity.get("customer_name", ""),
        "customer_id": identity.get("customer_id", ""),
        "email": identity.get("email", ""),
        "phone": identity.get("phone", ""),
        "address": identity.get("address", ""),
        "age_band": identity.get("age_band", ""),
        "employer": identity.get("employer", ""),
        "annual_income": identity.get("annual_income", ""),
        "product": sections.get("product", "").strip(),
        "facility": _parse_labeled_bullets(sections.get("amount and financials", "")),
        "attached_documents": _parse_plain_bullets(
            sections.get("attached documents", "")
        ),
        "narrative": sections.get("applicant statement", "").strip(),
    }


def read_application_manifest(out: Path) -> dict[str, Any]:
    path = out / "manifest.json"
    if not path.is_file():
        return {"documents": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"documents": []}
    if not isinstance(data, dict):
        return {"documents": []}
    documents = data.get("documents")
    if not isinstance(documents, list):
        data = dict(data)
        data["documents"] = []
    return data


def load_existing_slots(out: Path) -> dict[str, dict[str, Any]]:
    slots: dict[str, dict[str, Any]] = {}
    manifest = read_application_manifest(out)
    for item in manifest.get("documents") or []:
        if not isinstance(item, dict):
            continue
        slot = str(item.get("slot") or item.get("intended_outcome") or "")
        if slot not in APPLICATION_TYPES:
            continue
        application_id = str(item.get("application_id") or "")
        filename = str(item.get("filename") or "")
        if not filename and re.fullmatch(APPLICATION_ID_RE, application_id):
            filename = application_filename(application_id)
        path = out / filename if filename else None
        record = dict(item)
        if path is not None and path.is_file():
            try:
                parsed = parse_application_markdown(path.read_text(encoding="utf-8"))
                record = {**parsed, **item}
            except TalosError:
                pass
        record["application_type"] = slot
        record["intended_outcome"] = str(item.get("intended_outcome") or slot)
        if filename:
            record["_filename"] = filename
        slots[slot] = record
    for kind in APPLICATION_TYPES:
        if kind in slots:
            continue
        path = out / f"{kind}.md"
        if not path.is_file():
            continue
        try:
            record = parse_application_markdown(path.read_text(encoding="utf-8"))
        except TalosError:
            record = {}
        record["application_type"] = kind
        record["intended_outcome"] = kind
        record["_filename"] = path.name
        slots[kind] = record
    return slots


def identity_keys(record: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    name = str(record.get("customer_name") or "").strip()
    if name:
        keys.add(name.casefold())
    for field in ("customer_id", "application_id"):
        value = str(record.get(field) or "").strip()
        if value:
            keys.add(value)
    email = str(record.get("email") or "").strip()
    if email:
        keys.add(email.casefold())
    return keys


def used_identities(
    existing: dict[str, dict[str, Any]],
    *,
    replacing: tuple[str, ...],
    pending: list[dict[str, Any]] | None = None,
) -> set[str]:
    used: set[str] = set()
    skip = set(replacing)
    for kind, record in existing.items():
        if kind in skip:
            continue
        used |= identity_keys(record)
    for record in pending or []:
        used |= identity_keys(record)
    return used


def allocate_application_id(used: set[str], *, year: int | None = None) -> str:
    year_value = year if year is not None else datetime.now(timezone.utc).year
    for number in range(1, 1_000_000):
        candidate = f"CA-{year_value}-{number:06d}"
        if candidate not in used and not contains_forbidden_outcome_token(candidate):
            return candidate
    raise TalosError("no free application_id in CA-YYYY-NNNNNN space", exit_code=1)


def allocate_customer_id(used: set[str]) -> str:
    for _ in range(64):
        candidate = f"SYN-{secrets.randbelow(1_000_000):06d}"
        if candidate not in used:
            return candidate
    raise TalosError("could not allocate a unique SYN-###### customer_id", exit_code=1)


def validate_record(
    record: dict[str, Any],
    *,
    application_type: str,
    used: set[str],
    required_id: str,
    product_family: str | None = None,
) -> list[str]:
    errors: list[str] = []
    missing = [key for key in REQUIRED_JSON_KEYS if key not in record]
    if missing:
        errors.append(f"missing keys: {', '.join(missing)}")
        return errors

    application_id = str(record.get("application_id") or "")
    if application_id != required_id:
        errors.append(f"application_id must be {required_id!r}, got {application_id!r}")
    if not re.fullmatch(APPLICATION_ID_RE, application_id):
        errors.append(f"application_id {application_id!r} is not CA-YYYY-NNNNNN")
    if contains_forbidden_outcome_token(application_id):
        errors.append(
            f"application_id {application_id!r} contains a forbidden outcome token"
        )
    customer_id = str(record.get("customer_id") or "")
    if not re.fullmatch(CUSTOMER_ID_RE, customer_id):
        errors.append(f"customer_id {customer_id!r} must match SYN-######")
    email = str(record.get("email") or "")
    if not email.lower().endswith(f"@{EMAIL_DOMAIN}"):
        errors.append(f"email must use @{EMAIL_DOMAIN}, got {email!r}")

    family = product_family or str(record.get("product_family") or "")
    if family not in PRODUCT_FAMILIES:
        errors.append(f"unknown product_family {family!r}")
        return errors
    required_docs = PRODUCT_REQUIRED_DOCUMENTS[family]
    expected_product = PRODUCT_FAMILY_LABEL[family]
    if str(record.get("product") or "").strip() != expected_product:
        errors.append(f"product must be {expected_product!r}")

    facility = record.get("facility")
    if not isinstance(facility, dict) or not facility:
        errors.append("facility must be a non-empty mapping")
    else:
        for key in REQUIRED_FACILITY_KEYS:
            if key not in facility or facility[key] in (None, ""):
                errors.append(f"facility.{key} is required")
        errors.extend(
            facility_limit_errors(
                facility,
                application_type=application_type,
                product_family=family,
            )
        )

    attached = record.get("attached_documents")
    if not isinstance(attached, list) or not all(
        isinstance(item, str) and item.strip() for item in attached
    ):
        errors.append("attached_documents must be a list of titles")
    else:
        attached_set = {item.strip() for item in attached}
        required_set = set(required_docs)
        extra = attached_set - required_set
        if extra:
            errors.append(f"unknown attached document titles: {sorted(extra)}")
        if application_type == "missing-data":
            if attached_set >= required_set:
                errors.append(
                    "missing-data must omit at least one required document title"
                )
        elif attached_set != required_set:
            errors.append(
                f"{application_type} must list the full required set "
                f"{sorted(required_set)}, got {sorted(attached_set)}"
            )

    for field in (
        "customer_name",
        "address",
        "phone",
        "employer",
        "product",
        "narrative",
    ):
        if not str(record.get(field) or "").strip():
            errors.append(f"{field} is required")

    blob = json.dumps(record, ensure_ascii=False)
    if SSN_RE.search(blob) or NATIONAL_ID_RE.search(blob):
        errors.append("record looks like real national-id / SSN; use fictional values")
    filing_text = " ".join(
        str(record.get(field) or "")
        for field in ("narrative", "product", "customer_name", "employer", "address")
    )
    if JUDGEMENT_LEAK_RE.search(filing_text):
        errors.append(
            "filing fields must not contain ApplicationType or judgement labels"
        )

    keys = identity_keys(record)
    overlap = keys & used
    if overlap:
        errors.append(f"identity not unique vs manifest: {sorted(overlap)}")
    return errors


def validate_filing_markdown(markdown: str, record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    application_id = str(record.get("application_id") or "")
    expected = credit_application_heading(application_id)
    first = first_visible_line(markdown)
    if first != expected:
        errors.append(f"first visible line must be {expected!r}, got {first!r}")
    if _yaml_prefix_present(markdown):
        errors.append("YAML front matter is forbidden")
    if JUDGEMENT_LEAK_RE.search(markdown):
        errors.append("filing must not contain ApplicationType or judgement labels")
    if contains_forbidden_outcome_token(application_id):
        errors.append("application_id encodes an outcome token")
    if re.fullmatch(
        APPLICATION_ID_RE, application_id
    ) and contains_forbidden_outcome_token(application_filename(application_id)):
        errors.append("filename encodes an outcome token")
    lower = markdown.lower()
    for needle in ("identity", "product", "attached document"):
        if needle not in lower:
            errors.append(f"customer filing is missing {needle} section")
    amount = ""
    facility = record.get("facility")
    if isinstance(facility, dict):
        amount = str(facility.get("loan_amount") or "")
    if amount and amount not in markdown:
        errors.append("customer filing is missing the requested amount")
    for title in record.get("attached_documents") or []:
        if str(title) not in markdown:
            errors.append(f"attached document title missing from filing: {title}")
    return errors


def render_application(
    record: dict[str, Any],
    template_path: Path,
    *,
    application_type: str,
) -> RenderedApplication:
    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )
    try:
        markdown = env.get_template(template_path.name).render(app=record)
    except TemplateError as exc:
        raise TalosError(f"Failed to render application: {exc}", exit_code=1) from exc
    if not markdown.endswith("\n"):
        markdown += "\n"
    leak_errors = validate_filing_markdown(markdown, record)
    if leak_errors:
        raise TalosError(
            "rendered application is not a customer filing: " + "; ".join(leak_errors),
            exit_code=1,
        )
    digest = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    application_id = str(record["application_id"])
    return RenderedApplication(
        application_type=application_type,
        filename=application_filename(application_id),
        markdown=markdown,
        content_sha256=digest,
        record=record,
    )


def build_application_manifest(
    existing: dict[str, dict[str, Any]],
    rendered: list[RenderedApplication],
    *,
    generated_at: str,
    container: str,
) -> dict[str, Any]:
    by_slot: dict[str, dict[str, Any]] = {}
    for slot, record in existing.items():
        if slot not in APPLICATION_TYPES:
            continue
        application_id = str(record.get("application_id") or "")
        filename = str(record.get("_filename") or record.get("filename") or "")
        if not filename and re.fullmatch(APPLICATION_ID_RE, application_id):
            filename = application_filename(application_id)
        by_slot[slot] = {
            "slot": slot,
            "application_id": application_id,
            "intended_outcome": str(record.get("intended_outcome") or slot),
            "filename": filename,
            "blob_path": filename,
            "content_sha256": record.get("content_sha256"),
            "customer_name": record.get("customer_name"),
            "customer_id": record.get("customer_id"),
            "product_family": record.get("product_family"),
        }
    for item in rendered:
        application_id = str(item.record["application_id"])
        by_slot[item.application_type] = {
            "slot": item.application_type,
            "application_id": application_id,
            "intended_outcome": item.application_type,
            "filename": item.filename,
            "blob_path": item.filename,
            "content_sha256": item.content_sha256,
            "customer_name": item.record["customer_name"],
            "customer_id": item.record["customer_id"],
            "product_family": item.record.get("product_family"),
        }
    documents = [by_slot[kind] for kind in APPLICATION_TYPES if kind in by_slot]
    return {
        "generated_at": generated_at,
        "watermark": WATERMARK,
        "container": container,
        "documents": documents,
    }


def write_applications(
    out: Path,
    rendered: list[RenderedApplication],
    manifest: dict[str, Any],
    echo: Echo,
    *,
    stale_filenames: set[str] | None = None,
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    keep = {item.filename for item in rendered}
    for name in stale_filenames or []:
        if name in keep:
            continue
        path = out / name
        if path.is_file():
            path.unlink()
            echo(f"removed {path}")
    for item in rendered:
        path = out / item.filename
        path.write_text(item.markdown, encoding="utf-8")
        echo(f"wrote {path}")
    manifest_path = out / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    echo(f"wrote {manifest_path}")


def application_blob_metadata(item: RenderedApplication) -> dict[str, str]:
    return {
        "content_sha256": item.content_sha256,
        "application_id": str(item.record["application_id"]),
        "synthetic": "true",
    }


def run_generate_application(
    config: ApplicationGenerateConfig,
    echo: Echo = print,
    *,
    completer: ChatCompleter | None = None,
    blob_store: BlobStore | None = None,
    credential: TokenCredential | None = None,
) -> list[RenderedApplication]:
    types = config.types
    if not types:
        raise TalosError("exactly one of --type or --all is required", exit_code=1)
    unknown = [kind for kind in types if kind not in APPLICATION_TYPES]
    if unknown:
        raise TalosError(
            f"unknown application type {unknown[0]!r}",
            exit_code=1,
        )

    existing = load_existing_slots(config.out)
    occupied = [kind for kind in types if kind in existing]
    if occupied and not config.force:
        names = ", ".join(occupied)
        raise TalosError(
            f"application slot exists ({names}); pass --force to overwrite",
            exit_code=1,
        )

    if config.dry_run:
        echo("dry-run: no LLM call")
        used = used_identities(existing, replacing=types)
        for kind in types:
            application_id = allocate_application_id(used)
            used.add(application_id)
            echo(
                f"dry-run: would generate slot {kind} -> "
                f"{config.out / application_filename(application_id)}"
            )
        if not config.local_only:
            echo("dry-run: no blobs uploaded")
        return []

    env = resolve_env(use_terraform=config.use_terraform)
    project_endpoint = (
        config.project_endpoint or env.get("AZURE_AI_PROJECT_ENDPOINT") or ""
    )
    if completer is None and not project_endpoint:
        raise TalosError(
            "Azure environment is not configured (missing AZURE_AI_PROJECT_ENDPOINT). "
            "Set the variable, run `gmake infra-create` (writes `infra/outputs.json`), "
            "or pass --dry-run.",
            exit_code=2,
        )

    want_azure = not config.local_only
    generate_env = resolve_generate_env(use_terraform=config.use_terraform)
    store = blob_store
    if want_azure and store is None:
        if not azure_generate_configured(generate_env, config.account_url):
            raise TalosError(
                "Azure environment is not configured "
                "(missing AZURE_STORAGE_ACCOUNT_URL or AZURE_STORAGE_CONNECTION_STRING). "
                "Set the variables, run `gmake infra-create`, or pass --local-only.",
                exit_code=2,
            )

    chat = completer or _default_completer(
        project_endpoint,
        config.chat_deployment,
        credential=credential,
    )
    paths = _prompt_paths(config)
    system_prompt = paths.system.read_text(encoding="utf-8")
    schema_text = paths.schema.read_text(encoding="utf-8")
    facts_text = config.facts_path.read_text(encoding="utf-8")
    user_template = _jinja_env(paths.user.parent).get_template(paths.user.name)

    used_families = {
        str(record.get("product_family"))
        for slot, record in existing.items()
        if slot not in types and record.get("product_family") in PRODUCT_FAMILIES
    }
    rendered: list[RenderedApplication] = []
    pending_records: list[dict[str, Any]] = []
    stale_filenames: set[str] = set()
    for kind in types:
        used = used_identities(existing, replacing=types, pending=pending_records)
        application_id = allocate_application_id(used)
        customer_id = allocate_customer_id(used)
        product_family = assign_product_family(kind, used_families)
        used_families.add(product_family)
        attached, _omitted = attached_documents_for(kind, product_family)
        record = _complete_one(
            chat,
            user_template=user_template,
            system_prompt=system_prompt,
            schema_text=schema_text,
            facts_text=facts_text,
            application_type=kind,
            application_id=application_id,
            customer_id=customer_id,
            product_family=product_family,
            attached_documents=attached,
            used=used,
            echo=echo,
        )
        pending_records.append(record)
        rendered.append(
            render_application(record, paths.template, application_type=kind)
        )
        previous = existing.get(kind) or {}
        old_name = str(previous.get("_filename") or previous.get("filename") or "")
        if old_name:
            stale_filenames.add(old_name)
        stale_filenames.add(f"{kind}.md")

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    kept_existing = {
        slot: record for slot, record in existing.items() if slot not in types
    }
    manifest = build_application_manifest(
        kept_existing,
        rendered,
        generated_at=generated_at,
        container=config.container,
    )
    write_applications(
        config.out,
        rendered,
        manifest,
        echo,
        stale_filenames=stale_filenames,
    )

    if want_azure:
        if store is None:
            store = open_blob_store(
                generate_env,
                container=config.container,
                account_url=config.account_url,
                credential=credential,
            )
        _upload_applications(store, rendered, echo=echo)

    return rendered


def _complete_one(
    chat: ChatCompleter,
    *,
    user_template: Any,
    system_prompt: str,
    schema_text: str,
    facts_text: str,
    application_type: str,
    application_id: str,
    customer_id: str,
    product_family: str,
    attached_documents: tuple[str, ...],
    used: set[str],
    echo: Echo,
) -> dict[str, Any]:
    last_errors: list[str] = []
    product_label = PRODUCT_FAMILY_LABEL[product_family]
    for attempt in range(1, APPLICATION_LLM_ATTEMPTS + 1):
        user = user_template.render(
            application_type=application_type,
            application_id=application_id,
            customer_id=customer_id,
            product_family=product_family,
            product_label=product_label,
            attached_documents=attached_documents,
            watermark=WATERMARK,
            schema=schema_text,
            facts_yaml=facts_text,
            facility_hint=FACILITY_PROMPT_HINTS[product_family],
            used_identities=sorted(used),
            previous_errors=last_errors,
        )
        echo(f"generating slot {application_type} ({application_id}) attempt {attempt}")
        try:
            raw = chat.complete(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user},
                ]
            )
            record = parse_llm_json(raw)
            record["application_id"] = application_id
            record["customer_id"] = str(record.get("customer_id") or customer_id)
            record["product_family"] = product_family
            record["product"] = product_label
            record["attached_documents"] = list(attached_documents)
            for leak_key in OPERATOR_RECORD_KEYS:
                record.pop(leak_key, None)
            errors = validate_record(
                record,
                application_type=application_type,
                used=used,
                required_id=application_id,
                product_family=product_family,
            )
        except TalosError as exc:
            errors = [str(exc)]
            record = {}
        if not errors:
            return record
        last_errors = errors
        echo(f"validation failed: {'; '.join(errors)}")
    raise TalosError(
        "application generation failed after retry:\n- " + "\n- ".join(last_errors),
        exit_code=1,
    )


def _upload_applications(
    store: BlobStore,
    rendered: list[RenderedApplication],
    *,
    echo: Echo,
) -> None:
    try:
        store.ensure_container()
        for item in rendered:
            url = store.upload_markdown(
                item.filename,
                item.markdown.encode("utf-8"),
                application_blob_metadata(item),
            )
            echo(
                f"{item.record['application_id']}  {item.filename}  blob={url}  uploaded"
            )
    except TalosError:
        raise
    except Exception as exc:
        raise TalosError(f"Blob upload failed: {exc}", exit_code=1) from exc


@dataclass(frozen=True)
class _PromptPaths:
    schema: Path
    system: Path
    user: Path
    template: Path


def _prompt_paths(config: ApplicationGenerateConfig) -> _PromptPaths:
    root = repo_root()
    return _PromptPaths(
        schema=config.schema_path or (root / DEFAULT_APPLICATION_SCHEMA_RELATIVE),
        system=config.system_prompt_path
        or (root / DEFAULT_APPLICATION_SYSTEM_PROMPT_RELATIVE),
        user=config.user_prompt_path
        or (root / DEFAULT_APPLICATION_USER_PROMPT_RELATIVE),
        template=config.template_path or (root / DEFAULT_APPLICATION_TEMPLATE_RELATIVE),
    )


def _jinja_env(directory: Path) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(directory)),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )


def _default_completer(
    project_endpoint: str,
    model: str,
    *,
    credential: TokenCredential | None,
) -> FoundryChatCompleter:
    from talos.rest import RequestsRest

    cred = credential or DefaultAzureCredential()
    return FoundryChatCompleter(RequestsRest(cred), project_endpoint, model)


def default_application_out() -> Path:
    return repo_root() / DEFAULT_APPLICATION_OUTPUT_RELATIVE
