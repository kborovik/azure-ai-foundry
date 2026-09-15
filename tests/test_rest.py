from __future__ import annotations

import pytest
import requests
from azure.core.credentials import AccessToken

from talos.errors import TalosError
from talos.rest import RequestsRest

pytestmark = pytest.mark.unit


class _TokenCredential:
    def get_token(self, *scopes: str, **kwargs: object) -> AccessToken:
        return AccessToken("token", 0)


class _BoomSession:
    def request(self, *args: object, **kwargs: object) -> object:
        raise requests.ConnectionError("dns fail")


def test_requests_rest_wraps_connection_error() -> None:
    rest = RequestsRest(_TokenCredential(), session=_BoomSession())  # type: ignore[arg-type]
    with pytest.raises(TalosError, match="GET http://example.test failed") as exc:
        rest.request("GET", "http://example.test", scope="https://example/.default")
    assert exc.value.exit_code == 1
    assert isinstance(exc.value.__cause__, requests.ConnectionError)
