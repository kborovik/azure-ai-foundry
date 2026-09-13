from __future__ import annotations

import os
import subprocess
from collections.abc import MutableMapping
from pathlib import Path

from talos.constants import REQUIRED_ENV
from talos.errors import TalosError


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


def parse_azd_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def load_dotenv_file(path: Path | None = None) -> dict[str, str]:
    dotenv_path = path or (repo_root() / ".env")
    if not dotenv_path.is_file():
        return {}
    try:
        text = dotenv_path.read_text(encoding="utf-8")
    except OSError:
        return {}
    return parse_azd_values(text)


def load_azd_env() -> dict[str, str]:
    try:
        proc = subprocess.run(
            ["azd", "env", "get-values"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return {}
    if proc.returncode != 0:
        return {}
    return parse_azd_values(proc.stdout)


def fill_missing(env: MutableMapping[str, str], extra: dict[str, str]) -> None:
    for key, value in extra.items():
        if value and not env.get(key):
            env[key] = value


def apply_dotenv(
    env: MutableMapping[str, str] | None = None,
    path: Path | None = None,
) -> MutableMapping[str, str]:
    target: MutableMapping[str, str] = os.environ if env is None else env
    fill_missing(target, load_dotenv_file(path))
    return target


def resolve_env(*, use_azd: bool) -> dict[str, str]:
    env = dict(os.environ)
    fill_missing(env, load_dotenv_file())
    if not use_azd:
        return env
    if not missing_required(env):
        return env
    fill_missing(env, load_azd_env())
    return env


def azure_generate_configured(env: dict[str, str], account_url: str = "") -> bool:
    return bool(
        account_url
        or env.get("AZURE_STORAGE_ACCOUNT_URL")
        or env.get("AZURE_STORAGE_CONNECTION_STRING")
    )


def resolve_generate_env(*, use_azd: bool) -> dict[str, str]:
    env = dict(os.environ)
    fill_missing(env, load_dotenv_file())
    if not use_azd:
        return env
    if azure_generate_configured(env):
        return env
    fill_missing(env, load_azd_env())
    return env


def missing_required(env: dict[str, str]) -> list[str]:
    return [name for name in REQUIRED_ENV if not env.get(name)]


def require_env(env: dict[str, str]) -> None:
    missing = missing_required(env)
    if missing:
        names = ", ".join(missing)
        raise TalosError(
            f"Azure environment is not configured (missing {names}). "
            "Set the variables, add them to .env, run from an azd environment, "
            "or pass CLI flags.",
            exit_code=2,
        )
