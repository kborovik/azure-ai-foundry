from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from azure.core.credentials import TokenCredential

from talos.errors import TalosError

if TYPE_CHECKING:
    import requests


@dataclass(frozen=True)
class RestResponse:
    status_code: int
    json: Any
    text: str
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


class RestClient(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        scope: str,
        json_body: Any | None = None,
        content_type: str = "application/json",
        timeout: float = 60.0,
    ) -> RestResponse: ...


class RequestsRest:
    def __init__(
        self,
        credential: TokenCredential,
        session: requests.Session | None = None,
    ) -> None:
        import requests as requests_lib

        self._credential = credential
        self._session = session or requests_lib.Session()

    def request(
        self,
        method: str,
        url: str,
        *,
        scope: str,
        json_body: Any | None = None,
        content_type: str = "application/json",
        timeout: float = 60.0,
    ) -> RestResponse:
        import requests

        token = self._credential.get_token(scope)
        headers = {
            "Authorization": f"Bearer {token.token}",
            "Content-Type": content_type,
        }
        kwargs: dict[str, Any] = {"headers": headers, "timeout": timeout}
        if json_body is not None:
            if content_type == "application/json":
                kwargs["json"] = json_body
            else:
                kwargs["data"] = json.dumps(json_body)
        try:
            response = self._session.request(method, url, **kwargs)
        except requests.RequestException as exc:
            raise TalosError(f"{method} {url} failed: {exc}", exit_code=1) from exc
        body: Any = None
        if response.content:
            try:
                body = response.json()
            except ValueError:
                body = None
        return RestResponse(
            status_code=response.status_code,
            json=body,
            text=response.text,
            headers={k: v for k, v in response.headers.items()},
        )


class Clock(Protocol):
    def sleep(self, seconds: float) -> None: ...

    def monotonic(self) -> float: ...


class SystemClock:
    def sleep(self, seconds: float) -> None:
        import time

        time.sleep(seconds)

    def monotonic(self) -> float:
        import time

        return time.monotonic()


def raise_for_status(response: RestResponse, action: str) -> None:
    if response.ok:
        return
    detail = _short_error(response)
    raise TalosError(f"{action} failed ({response.status_code}): {detail}")


def _short_error(response: RestResponse) -> str:
    if isinstance(response.json, dict):
        error = response.json.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])[:500]
        if response.json.get("message"):
            return str(response.json["message"])[:500]
    text = (response.text or "").strip()
    return text[:500] if text else "no error body"
