from __future__ import annotations

import os
import subprocess
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


def resolve_env(*, use_azd: bool) -> dict[str, str]:
    env = dict(os.environ)
    if not use_azd:
        return env
    missing = [name for name in REQUIRED_ENV if not env.get(name)]
    if not missing:
        return env
    for key, value in load_azd_env().items():
        env.setdefault(key, value)
    return env


def missing_required(env: dict[str, str]) -> list[str]:
    return [name for name in REQUIRED_ENV if not env.get(name)]


def require_env(env: dict[str, str]) -> None:
    missing = missing_required(env)
    if missing:
        names = ", ".join(missing)
        raise TalosError(
            f"Azure environment is not configured (missing {names}). "
            "Set the variables, run from an azd environment, or pass CLI flags.",
            exit_code=2,
        )
