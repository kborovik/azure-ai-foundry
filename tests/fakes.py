from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from talos.rest import RestResponse


@dataclass
class RecordedCall:
    method: str
    url: str
    scope: str
    json_body: Any
    content_type: str


class FakeRest:
    def __init__(self) -> None:
        self.calls: list[RecordedCall] = []
        self._script: list[
            tuple[str, str, RestResponse | Callable[[], RestResponse]]
        ] = []

    def expect(
        self,
        method: str,
        url_part: str,
        response: RestResponse | Callable[[], RestResponse],
    ) -> FakeRest:
        self._script.append((method.upper(), url_part, response))
        return self

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
        self.calls.append(
            RecordedCall(
                method=method.upper(),
                url=url,
                scope=scope,
                json_body=json_body,
                content_type=content_type,
            )
        )
        for index, (expected_method, url_part, response) in enumerate(self._script):
            if expected_method == method.upper() and url_part in url:
                self._script.pop(index)
                return response() if callable(response) else response
        raise AssertionError(f"unexpected {method.upper()} {url}")

    @property
    def pending(self) -> int:
        return len(self._script)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@dataclass
class FakeAgents:
    version: str = "3"
    agent: dict[str, Any] = field(default_factory=dict)
    created: dict[str, Any] | None = None
    pinned: tuple[str, str] | None = None

    def create_version(self, **kwargs: Any) -> str:
        self.created = kwargs
        return self.version

    def get_agent(self, agent_name: str) -> dict[str, Any]:
        return self.agent or {"name": agent_name, "agent_endpoint": {}}

    def pin_version(self, agent_name: str, version: str) -> None:
        self.pinned = (agent_name, version)


def json_response(status_code: int, body: Any | None = None) -> RestResponse:
    return RestResponse(
        status_code=status_code, json=body, text="" if body is None else str(body)
    )
