from __future__ import annotations

from pathlib import Path

import click

from talos import __version__
from talos.constants import (
    DEFAULT_AGENT_NAME,
    DEFAULT_CHAT_DEPLOYMENT,
    DEFAULT_CONNECTION_NAME,
    DEFAULT_CONTAINER,
    DEFAULT_EMBEDDING_DEPLOYMENT,
    DEFAULT_INSTRUCTIONS_RELATIVE,
    DEFAULT_KNOWLEDGE_BASE,
    DEFAULT_KNOWLEDGE_SOURCE,
)
from talos.env import require_env, resolve_env
from talos.errors import TalosError
from talos.provision import DeployConfig, run_deploy


@click.group()
@click.version_option(version=__version__, prog_name="talos")
def cli() -> None:
    """Deploy and test the credit-policy agent on Microsoft Foundry."""


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
    "--no-azd",
    is_flag=True,
    help="Do not fill missing env vars from `azd env get-values`.",
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
    no_azd: bool,
) -> None:
    """Provision Foundry IQ (knowledge source, indexer, knowledge base, MCP connection, agent)."""
    try:
        env = resolve_env(use_azd=not no_azd)
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
            container=container,
            knowledge_source=knowledge_source,
            knowledge_base=knowledge_base,
            agent_name=agent_name,
            connection_name=connection_name,
            chat_deployment=chat_deployment,
            embedding_deployment=embedding_deployment,
            instructions_path=instructions_path,
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
