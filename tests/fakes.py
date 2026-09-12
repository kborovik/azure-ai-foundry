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


@dataclass
class FakeBlob:
    data: bytes
    metadata: dict[str, str]
    content_md5: bytes | None = None


class FakeBlobStore:
    def __init__(
        self,
        account_url: str = "https://stcpdemo.blob.core.windows.net",
        container: str = "credit-policies",
    ) -> None:
        self.account_url = account_url
        self.container = container
        self.blobs: dict[str, FakeBlob] = {}
        self.container_created = False
        self.public_access: str | None = "unset"
        self.uploads: list[str] = []
        self.sha_lookups: list[str] = []
        self.fail_on_upload = False

    def ensure_container(self) -> None:
        self.container_created = True
        self.public_access = None

    def existing_sha256(self, blob_name: str) -> str | None:
        self.sha_lookups.append(blob_name)
        blob = self.blobs.get(blob_name)
        if blob is None:
            return None
        digest = blob.metadata.get("content_sha256")
        return digest.lower() if digest else None

    def blob_url(self, blob_name: str) -> str:
        return f"{self.account_url}/{self.container}/{blob_name}"

    def upload_markdown(
        self, blob_name: str, data: bytes, metadata: dict[str, str]
    ) -> str:
        if self.fail_on_upload:
            raise RuntimeError("simulated upload failure")
        self.blobs[blob_name] = FakeBlob(data=data, metadata=dict(metadata))
        self.uploads.append(blob_name)
        return self.blob_url(blob_name)


def json_response(status_code: int, body: Any | None = None) -> RestResponse:
    return RestResponse(
        status_code=status_code, json=body, text="" if body is None else str(body)
    )
