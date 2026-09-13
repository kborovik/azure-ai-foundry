from __future__ import annotations

from pathlib import Path

import click

from talos import __version__
from talos.constants import (
    APPLICATION_TYPES,
    DEFAULT_AGENT_NAME,
    DEFAULT_APPLICATION_CONTAINER,
    DEFAULT_APPLICATION_KNOWLEDGE_SOURCE,
    DEFAULT_APPLICATION_OUTPUT_RELATIVE,
    DEFAULT_CHAT_DEPLOYMENT,
    DEFAULT_CONNECTION_NAME,
    DEFAULT_CONTAINER,
    DEFAULT_EMBEDDING_DEPLOYMENT,
    DEFAULT_FACTS_RELATIVE,
    DEFAULT_INSTRUCTIONS_RELATIVE,
    DEFAULT_KNOWLEDGE_BASE,
    DEFAULT_KNOWLEDGE_SOURCE,
    DEFAULT_OUTPUT_RELATIVE,
    DEFAULT_TEMPLATES_RELATIVE,
)
from talos.env import repo_root, require_env, resolve_env
from talos.errors import TalosError
from talos.generate import GenerateConfig, run_generate
from talos.provision import DeployConfig, run_deploy


@click.group()
@click.version_option(version=__version__, prog_name="talos")
def cli() -> None:
    """Generate, deploy, and test the credit-policy agent on Microsoft Foundry."""


@cli.group(invoke_without_command=True)
@click.pass_context
def generate(ctx: click.Context) -> None:
    """Render synthetic credit policies or client applications. Does not run deploy."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        raise SystemExit(2)


@generate.command("policy")
@click.option(
    "--out",
    type=click.Path(path_type=Path, file_okay=False),
    default=None,
    help=f"Output directory. Default {DEFAULT_OUTPUT_RELATIVE}.",
)
@click.option(
    "--facts",
    "facts_path",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help=f"Facts YAML. Default {DEFAULT_FACTS_RELATIVE}.",
)
@click.option(
    "--templates",
    "templates_dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=None,
    help=f"Jinja template directory. Default {DEFAULT_TEMPLATES_RELATIVE}.",
)
@click.option("--container", default=DEFAULT_CONTAINER, show_default=True)
@click.option(
    "--account-url",
    default=None,
    help="Storage account URL. Default $AZURE_STORAGE_ACCOUNT_URL.",
)
@click.option(
    "--local-only",
    is_flag=True,
    help="Write local files only; do not upload blobs.",
)
@click.option(
    "--azure-only",
    is_flag=True,
    help="Upload blobs only; do not write local files.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Render and log paths without writing or uploading.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Upload even if content_sha256 matches (Azure path).",
)
@click.option(
    "--fail-if-missing-azure",
    is_flag=True,
    help="Exit 2 if Azure storage is not configured.",
)
@click.option(
    "--no-terraform",
    is_flag=True,
    help="Do not fill missing env vars from `infra/outputs.json`.",
)
def generate_policy(
    out: Path | None,
    facts_path: Path | None,
    templates_dir: Path | None,
    container: str,
    account_url: str | None,
    local_only: bool,
    azure_only: bool,
    dry_run: bool,
    force: bool,
    fail_if_missing_azure: bool,
    no_terraform: bool,
) -> None:
    """Render synthetic credit-policy Markdown. Does not run the Search indexer or deploy."""
    try:
        root = repo_root()
        config = GenerateConfig(
            out=out or (root / DEFAULT_OUTPUT_RELATIVE),
            facts_path=facts_path or (root / DEFAULT_FACTS_RELATIVE),
            templates_dir=templates_dir or (root / DEFAULT_TEMPLATES_RELATIVE),
            container=container,
            account_url=account_url or "",
            local_only=local_only,
            azure_only=azure_only,
            dry_run=dry_run,
            force=force,
            fail_if_missing_azure=fail_if_missing_azure,
            use_terraform=not no_terraform,
        )
        run_generate(config, echo=click.echo)
    except TalosError as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(exc.exit_code) from exc


@generate.command("application")
@click.option(
    "--type",
    "application_type",
    type=click.Choice(APPLICATION_TYPES, case_sensitive=True),
    default=None,
    help="Generate one ApplicationType slot.",
)
@click.option(
    "--all",
    "all_types",
    is_flag=True,
    help="Generate all three ApplicationType slots with unique identities.",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path, file_okay=False),
    default=None,
    help=f"Output directory. Default {DEFAULT_APPLICATION_OUTPUT_RELATIVE}.",
)
@click.option(
    "--facts",
    "facts_path",
    type=click.Path(path_type=Path, dir_okay=False),
    default=None,
    help=f"Facts YAML. Default {DEFAULT_FACTS_RELATIVE}.",
)
@click.option(
    "--container",
    default=DEFAULT_APPLICATION_CONTAINER,
    show_default=True,
)
@click.option(
    "--account-url",
    default=None,
    help="Storage account URL. Default $AZURE_STORAGE_ACCOUNT_URL.",
)
@click.option(
    "--local-only",
    is_flag=True,
    help="Write local files only; do not upload blobs.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print the plan without calling the LLM or writing files.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite an existing type slot.",
)
@click.option(
    "--no-terraform",
    is_flag=True,
    help="Do not fill missing env vars from `infra/outputs.json`.",
)
def generate_application_cmd(
    application_type: str | None,
    all_types: bool,
    out: Path | None,
    facts_path: Path | None,
    container: str,
    account_url: str | None,
    local_only: bool,
    dry_run: bool,
    force: bool,
    no_terraform: bool,
) -> None:
    """Generate unique synthetic client applications via Foundry gpt-5-mini. Does not PUT knowledge sources."""
    from talos.application import ApplicationGenerateConfig, run_generate_application

    try:
        if bool(application_type) == bool(all_types):
            raise TalosError("exactly one of --type or --all is required", exit_code=1)
        root = repo_root()
        env = resolve_env(use_terraform=not no_terraform)
        types = APPLICATION_TYPES if all_types else (application_type or "",)
        config = ApplicationGenerateConfig(
            out=out or (root / DEFAULT_APPLICATION_OUTPUT_RELATIVE),
            facts_path=facts_path or (root / DEFAULT_FACTS_RELATIVE),
            types=types,
            force=force,
            local_only=local_only,
            dry_run=dry_run,
            use_terraform=not no_terraform,
            account_url=account_url or "",
            container=container,
            project_endpoint=env.get("AZURE_AI_PROJECT_ENDPOINT") or "",
        )
        run_generate_application(config, echo=click.echo)
    except TalosError as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(exc.exit_code) from exc


@cli.command()
@click.option(
    "--search-endpoint",
    default=None,
    help="Azure AI Search endpoint. Default $AZURE_SEARCH_ENDPOINT.",
)
@click.option(
    "--project-endpoint",
    default=None,
    help="Foundry project endpoint. Default $AZURE_AI_PROJECT_ENDPOINT.",
)
@click.option(
    "--project-resource-id",
    default=None,
    help="Foundry project ARM id. Default $AZURE_AI_PROJECT_RESOURCE_ID.",
)
@click.option(
    "--storage-resource-id",
    default=None,
    help="Storage account ARM id. Default $AZURE_STORAGE_RESOURCE_ID.",
)
@click.option(
    "--ai-services-endpoint",
    default=None,
    help="Foundry resource endpoint for KS/KB resourceUri. Default $AZURE_AI_SERVICES_ENDPOINT.",
)
@click.option("--container", default=DEFAULT_CONTAINER, show_default=True)
@click.option("--knowledge-source", default=DEFAULT_KNOWLEDGE_SOURCE, show_default=True)
@click.option("--knowledge-base", default=DEFAULT_KNOWLEDGE_BASE, show_default=True)
@click.option("--agent-name", default=DEFAULT_AGENT_NAME, show_default=True)
@click.option("--connection-name", default=DEFAULT_CONNECTION_NAME, show_default=True)
@click.option("--chat-deployment", default=DEFAULT_CHAT_DEPLOYMENT, show_default=True)
@click.option(
    "--embedding-deployment", default=DEFAULT_EMBEDDING_DEPLOYMENT, show_default=True
)
@click.option(
    "--instructions",
    "instructions_path",
    type=click.Path(path_type=Path),
    default=None,
    help=f"Agent instructions file. Default {DEFAULT_INSTRUCTIONS_RELATIVE}.",
)
@click.option(
    "--wait", is_flag=True, help="Poll knowledge source status until indexing finishes."
)
@click.option(
    "--skip-indexer-run", is_flag=True, help="Do not POST-run the generated indexer."
)
@click.option(
    "--skip-endpoint-patch",
    is_flag=True,
    help="Do not PATCH agent_endpoint (also skipped when Activity protocol is already enabled).",
)
@click.option(
    "--dry-run", is_flag=True, help="Print the deploy plan without calling Azure."
)
@click.option(
    "--no-terraform",
    is_flag=True,
    help="Do not fill missing env vars from `infra/outputs.json`.",
)
def deploy(
    search_endpoint: str | None,
    project_endpoint: str | None,
    project_resource_id: str | None,
    storage_resource_id: str | None,
    ai_services_endpoint: str | None,
    container: str,
    knowledge_source: str,
    knowledge_base: str,
    agent_name: str,
    connection_name: str,
    chat_deployment: str,
    embedding_deployment: str,
    instructions_path: Path | None,
    wait: bool,
    skip_indexer_run: bool,
    skip_endpoint_patch: bool,
    dry_run: bool,
    no_terraform: bool,
) -> None:
    """Provision Foundry IQ (knowledge source, indexer, knowledge base, MCP connection, agent)."""
    try:
        env = resolve_env(use_terraform=not no_terraform)
        config = DeployConfig(
            search_endpoint=_first(search_endpoint, env.get("AZURE_SEARCH_ENDPOINT")),
            project_endpoint=_first(
                project_endpoint, env.get("AZURE_AI_PROJECT_ENDPOINT")
            ),
            project_resource_id=_first(
                project_resource_id, env.get("AZURE_AI_PROJECT_RESOURCE_ID")
            ),
            storage_resource_id=_first(
                storage_resource_id, env.get("AZURE_STORAGE_RESOURCE_ID")
            ),
            ai_services_endpoint=_first(
                ai_services_endpoint, env.get("AZURE_AI_SERVICES_ENDPOINT")
            ),
            storage_account_url=_first(env.get("AZURE_STORAGE_ACCOUNT_URL")),
            storage_connection_string=_first(
                env.get("AZURE_STORAGE_CONNECTION_STRING")
            ),
            container=container,
            application_container=DEFAULT_APPLICATION_CONTAINER,
            knowledge_source=knowledge_source,
            application_knowledge_source=DEFAULT_APPLICATION_KNOWLEDGE_SOURCE,
            knowledge_base=knowledge_base,
            agent_name=agent_name,
            connection_name=connection_name,
            chat_deployment=chat_deployment,
            embedding_deployment=embedding_deployment,
            instructions_path=instructions_path,
            policy_dir=repo_root() / DEFAULT_OUTPUT_RELATIVE,
            application_dir=repo_root() / DEFAULT_APPLICATION_OUTPUT_RELATIVE,
            wait=wait,
            skip_indexer_run=skip_indexer_run,
            skip_endpoint_patch=skip_endpoint_patch,
            dry_run=dry_run,
        )
        require_env(
            {
                "AZURE_SEARCH_ENDPOINT": config.search_endpoint,
                "AZURE_AI_PROJECT_ENDPOINT": config.project_endpoint,
                "AZURE_AI_PROJECT_RESOURCE_ID": config.project_resource_id,
                "AZURE_STORAGE_RESOURCE_ID": config.storage_resource_id,
                "AZURE_AI_SERVICES_ENDPOINT": config.ai_services_endpoint,
            }
        )
        run_deploy(config, echo=click.echo)
    except TalosError as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(exc.exit_code) from exc


@cli.command(
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.pass_context
def test(ctx: click.Context) -> None:
    """Run pytest. Extra args are forwarded (default marker: unit)."""
    args = list(ctx.args)
    if args in (["--help"], ["-h"]):
        click.echo(ctx.get_help())
        return
    import pytest

    raise SystemExit(pytest.main(args))


def _first(*values: str | None) -> str:
    for value in values:
        if value:
            return value
    return ""
