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

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateError
from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential

from talos.constants import (
    APPLICATION_ID_RE,
    APPLICATION_LLM_ATTEMPTS,
    APPLICATION_TYPE_ID_TOKEN,
    APPLICATION_TYPES,
    CORPUS_IDS,
    CUSTOMER_ID_RE,
    DEFAULT_APPLICATION_CONTAINER,
    DEFAULT_APPLICATION_OUTPUT_RELATIVE,
    DEFAULT_APPLICATION_SCHEMA_RELATIVE,
    DEFAULT_APPLICATION_SYSTEM_PROMPT_RELATIVE,
    DEFAULT_APPLICATION_TEMPLATE_RELATIVE,
    DEFAULT_APPLICATION_USER_PROMPT_RELATIVE,
    DEFAULT_CHAT_DEPLOYMENT,
    EMAIL_DOMAIN,
    FOUNDRY_SCOPE,
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

SLOT_FILENAME = {kind: f"{kind}.md" for kind in APPLICATION_TYPES}
REQUIRED_JSON_KEYS = (
    "application_id",
    "application_type",
    "expected_judgement",
    "expected_policy_ids",
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
    "missing_items",
)
REQUIRED_FACILITY_KEYS = ("loan_amount", "credit_score")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
NATIONAL_ID_RE = re.compile(r"\b\d{6}[- ]\d{4}\b")
FRONT_MATTER_RE = re.compile(r"^---\n(.*?)\n---", re.M | re.S)


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


def application_filename(application_type: str) -> str:
    try:
        return SLOT_FILENAME[application_type]
    except KeyError as exc:
        raise TalosError(
            f"unknown application type {application_type!r}", exit_code=1
        ) from exc


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


def parse_application_markdown(text: str) -> dict[str, Any]:
    if first_visible_line(text) != WATERMARK:
        raise TalosError(
            f"first visible line must be {WATERMARK!r}",
            exit_code=1,
        )
    match = FRONT_MATTER_RE.search(text)
    if match is None:
        raise TalosError(
            "application markdown is missing YAML front matter", exit_code=1
        )
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise TalosError(
            f"invalid application front matter: {exc}", exit_code=1
        ) from exc
    if not isinstance(data, dict):
        raise TalosError("application front matter must be a mapping", exit_code=1)
    return data


def load_existing_records(out: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    if not out.is_dir():
        return records
    for kind in APPLICATION_TYPES:
        path = out / application_filename(kind)
        if not path.is_file():
            continue
        try:
            records[kind] = parse_application_markdown(path.read_text(encoding="utf-8"))
        except TalosError:
            records[kind] = {"application_type": kind}
    return records


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


def allocate_application_id(application_type: str, used: set[str]) -> str:
    token = APPLICATION_TYPE_ID_TOKEN[application_type]
    for number in range(1, 100):
        candidate = f"CA-{token}-2026-{number:02d}"
        if candidate not in used:
            return candidate
    raise TalosError(
        f"no free application_id for type {application_type}",
        exit_code=1,
    )


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
) -> list[str]:
    errors: list[str] = []
    missing = [key for key in REQUIRED_JSON_KEYS if key not in record]
    if missing:
        errors.append(f"missing keys: {', '.join(missing)}")
        return errors

    if record.get("application_type") != application_type:
        errors.append(
            f"application_type must be {application_type!r}, "
            f"got {record.get('application_type')!r}"
        )
    if record.get("expected_judgement") != application_type:
        errors.append(
            f"expected_judgement must match type {application_type!r}, "
            f"got {record.get('expected_judgement')!r}"
        )
    application_id = str(record.get("application_id") or "")
    if application_id != required_id:
        errors.append(f"application_id must be {required_id!r}, got {application_id!r}")
    if not re.fullmatch(APPLICATION_ID_RE, application_id):
        errors.append(f"application_id {application_id!r} is not CA-{{TYPE}}-YYYY-NN")
    customer_id = str(record.get("customer_id") or "")
    if not re.fullmatch(CUSTOMER_ID_RE, customer_id):
        errors.append(f"customer_id {customer_id!r} must match SYN-######")
    email = str(record.get("email") or "")
    if not email.lower().endswith(f"@{EMAIL_DOMAIN}"):
        errors.append(f"email must use @{EMAIL_DOMAIN}, got {email!r}")

    policy_ids = record.get("expected_policy_ids")
    if not isinstance(policy_ids, list) or not policy_ids:
        errors.append("expected_policy_ids must be a non-empty list")
    else:
        for policy_id in policy_ids:
            if policy_id not in CORPUS_IDS:
                errors.append(f"unknown expected_policy_id {policy_id!r}")

    facility = record.get("facility")
    if not isinstance(facility, dict) or not facility:
        errors.append("facility must be a non-empty mapping")
    else:
        for key in REQUIRED_FACILITY_KEYS:
            if key not in facility or facility[key] in (None, ""):
                errors.append(f"facility.{key} is required")

    missing_items = record.get("missing_items")
    if not isinstance(missing_items, list) or not all(
        isinstance(item, str) for item in missing_items
    ):
        errors.append("missing_items must be a list of strings")
    elif application_type == "missing-data" and not missing_items:
        errors.append("missing-data applications require non-empty missing_items")
    elif application_type != "missing-data" and missing_items:
        errors.append(f"{application_type} applications must have empty missing_items")

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

    keys = identity_keys(record)
    overlap = keys & used
    if overlap:
        errors.append(f"identity not unique vs manifest: {sorted(overlap)}")
    return errors


def render_application(
    record: dict[str, Any],
    template_path: Path,
) -> RenderedApplication:
    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )
    try:
        markdown = env.get_template(template_path.name).render(
            app=record,
            watermark=WATERMARK,
        )
    except TemplateError as exc:
        raise TalosError(f"Failed to render application: {exc}", exit_code=1) from exc
    if not markdown.endswith("\n"):
        markdown += "\n"
    if first_visible_line(markdown) != WATERMARK:
        raise TalosError(
            f"rendered application first visible line must be {WATERMARK!r}",
            exit_code=1,
        )
    digest = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    kind = str(record["application_type"])
    return RenderedApplication(
        application_type=kind,
        filename=application_filename(kind),
        markdown=markdown,
        content_sha256=digest,
        record=record,
    )


def build_application_manifest(
    records: dict[str, dict[str, Any]],
    rendered: list[RenderedApplication],
    *,
    generated_at: str,
    container: str,
) -> dict[str, Any]:
    by_type = {
        str(item.get("application_type")): item
        for item in records.values()
        if item.get("application_type") in APPLICATION_TYPES
    }
    for item in rendered:
        by_type[item.application_type] = {
            "application_id": item.record["application_id"],
            "application_type": item.application_type,
            "filename": item.filename,
            "blob_path": item.filename,
            "content_sha256": item.content_sha256,
            "customer_name": item.record["customer_name"],
            "customer_id": item.record["customer_id"],
            "expected_judgement": item.record["expected_judgement"],
        }
    documents = [by_type[kind] for kind in APPLICATION_TYPES if kind in by_type]
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
) -> None:
    out.mkdir(parents=True, exist_ok=True)
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
        "application_type": item.application_type,
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

    existing = load_existing_records(config.out)
    occupied = [kind for kind in types if kind in existing]
    if occupied and not config.force:
        names = ", ".join(occupied)
        raise TalosError(
            f"application slot exists ({names}); pass --force to overwrite",
            exit_code=1,
        )

    if config.dry_run:
        echo("dry-run: no LLM call")
        for kind in types:
            echo(
                f"dry-run: would generate {kind} -> "
                f"{config.out / application_filename(kind)}"
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

    rendered: list[RenderedApplication] = []
    pending_records: list[dict[str, Any]] = []
    for kind in types:
        used = used_identities(existing, replacing=types, pending=pending_records)
        application_id = allocate_application_id(kind, used)
        customer_id = allocate_customer_id(used)
        record = _complete_one(
            chat,
            user_template=user_template,
            system_prompt=system_prompt,
            schema_text=schema_text,
            facts_text=facts_text,
            application_type=kind,
            application_id=application_id,
            customer_id=customer_id,
            used=used,
            echo=echo,
        )
        pending_records.append(record)
        rendered.append(render_application(record, paths.template))

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = build_application_manifest(
        existing,
        rendered,
        generated_at=generated_at,
        container=config.container,
    )
    write_applications(config.out, rendered, manifest, echo)

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
    used: set[str],
    echo: Echo,
) -> dict[str, Any]:
    last_errors: list[str] = []
    for attempt in range(1, APPLICATION_LLM_ATTEMPTS + 1):
        user = user_template.render(
            application_type=application_type,
            application_id=application_id,
            customer_id=customer_id,
            watermark=WATERMARK,
            schema=schema_text,
            facts_yaml=facts_text,
            used_identities=sorted(used),
            previous_errors=last_errors,
        )
        echo(f"generating {application_type} ({application_id}) attempt {attempt}")
        try:
            raw = chat.complete(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user},
                ]
            )
            record = parse_llm_json(raw)
            record["application_id"] = application_id
            record["application_type"] = application_type
            record["expected_judgement"] = application_type
            record["customer_id"] = str(record.get("customer_id") or customer_id)
            errors = validate_record(
                record,
                application_type=application_type,
                used=used,
                required_id=application_id,
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
