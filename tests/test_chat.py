from __future__ import annotations

from io import StringIO

import pytest
from click.testing import CliRunner

from talos.chat import (
    WAIT_LABEL,
    ChatConfig,
    NullWait,
    TtyWaitIndicator,
    ask,
    response_output_text,
    run_chat,
)
from talos.cli import cli
from talos.constants import DEFAULT_AGENT_NAME, FOUNDRY_SCOPE
from talos.errors import TalosError
from tests.fakes import FakeRest, json_response

pytestmark = pytest.mark.unit

PROJECT = "https://aif-cp-demo.services.ai.azure.com/api/projects/credit-policy-demo"


class RecordingWait:
    def __init__(self) -> None:
        self.events: list[str] = []

    def start(self) -> None:
        self.events.append("start")

    def stop(self) -> None:
        self.events.append("stop")


class Echo:
    def __init__(self) -> None:
        self.out: list[str] = []
        self.err: list[str] = []

    def __call__(self, message: object = "", err: bool = False, **_: object) -> None:
        target = self.err if err else self.out
        target.append("" if message is None else str(message))


def _config(**overrides: object) -> ChatConfig:
    values: dict[str, object] = dict(project_endpoint=PROJECT)
    values.update(overrides)
    return ChatConfig(**values)  # type: ignore[arg-type]


def _ok_body(text: str = "80%", response_id: str = "resp_1") -> dict:
    return {"id": response_id, "output_text": text}


def test_chat_help_documents_flags() -> None:
    result = CliRunner().invoke(cli, ["chat", "--help"])
    assert result.exit_code == 0
    for flag in (
        "--project-endpoint",
        "--agent-name",
        "--dry-run",
        "--no-terraform",
    ):
        assert flag in result.output
    assert "infra/outputs.json" in result.output


def test_chat_missing_project_endpoint_exits_2(clean_azure_env: None) -> None:
    result = CliRunner().invoke(cli, ["chat", "--no-terraform", "hello"])
    assert result.exit_code == 2
    assert "AZURE_AI_PROJECT_ENDPOINT" in result.output


def test_chat_dry_run_prints_plan_without_rest(
    clean_azure_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AZURE_AI_PROJECT_ENDPOINT", PROJECT)
    result = CliRunner().invoke(
        cli,
        ["chat", "--dry-run", "--no-terraform", "What is the max LTV?"],
    )
    assert result.exit_code == 0, result.output
    assert "dry-run chat" in result.output
    assert PROJECT in result.output
    assert DEFAULT_AGENT_NAME in result.output
    assert "What is the max LTV?" in result.output


def test_chat_one_shot_prints_answer(
    clean_azure_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    rest = FakeRest().expect(
        "POST",
        "/openai/v1/responses",
        json_response(200, _ok_body("80% owner-occupied")),
    )
    monkeypatch.setenv("AZURE_AI_PROJECT_ENDPOINT", PROJECT)
    monkeypatch.setattr("talos.chat.RequestsRest", lambda credential: rest)
    monkeypatch.setattr("azure.identity.DefaultAzureCredential", lambda: object())
    result = CliRunner().invoke(
        cli,
        ["chat", "--no-terraform", "What", "is", "the", "max", "LTV?"],
    )
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "80% owner-occupied"
    assert len(rest.calls) == 1
    call = rest.calls[0]
    assert call.method == "POST"
    assert call.url.endswith("/openai/v1/responses")
    assert call.scope == FOUNDRY_SCOPE
    assert call.json_body["input"] == "What is the max LTV?"
    assert call.json_body["agent_reference"] == {
        "name": DEFAULT_AGENT_NAME,
        "type": "agent_reference",
    }


def test_chat_empty_stdin_exits_1(
    clean_azure_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AZURE_AI_PROJECT_ENDPOINT", PROJECT)
    result = CliRunner().invoke(cli, ["chat", "--no-terraform"], input="")
    assert result.exit_code == 1
    assert "question is required" in result.output


def test_ask_posts_agent_reference() -> None:
    rest = FakeRest().expect(
        "POST",
        "/openai/v1/responses",
        json_response(200, _ok_body("cited answer", "resp_9")),
    )
    turn = ask(rest, _config(), "What is DSCR?")
    assert turn.text == "cited answer"
    assert turn.response_id == "resp_9"
    assert "previous_response_id" not in rest.calls[0].json_body


def test_ask_empty_output_raises() -> None:
    rest = FakeRest().expect(
        "POST",
        "/openai/v1/responses",
        json_response(200, {"id": "resp_empty", "output_text": "  "}),
    )
    with pytest.raises(TalosError, match="empty text") as exc:
        ask(rest, _config(), "hello")
    assert exc.value.exit_code == 1


def test_ask_http_error_raises() -> None:
    rest = FakeRest().expect(
        "POST",
        "/openai/v1/responses",
        json_response(500, {"error": {"message": "boom"}}),
    )
    with pytest.raises(TalosError, match="agent responses failed \\(500\\)"):
        ask(rest, _config(), "hello")


def test_response_output_text_prefers_output_text() -> None:
    assert response_output_text({"output_text": "direct"}) == "direct"


def test_response_output_text_joins_content_blocks() -> None:
    payload = {
        "output": [
            {"content": [{"text": "first"}, {"text": "second"}]},
            {"content": "skip"},
            "skip",
        ]
    }
    assert response_output_text(payload) == "first\nsecond"


def test_run_chat_repl_threads_previous_response_id() -> None:
    rest = (
        FakeRest()
        .expect(
            "POST",
            "/openai/v1/responses",
            json_response(200, _ok_body("one", "resp_a")),
        )
        .expect(
            "POST",
            "/openai/v1/responses",
            json_response(200, _ok_body("two", "resp_b")),
        )
    )
    lines = iter(["first question", "follow up", "/quit"])

    def prompt(_label: str) -> str:
        return next(lines)

    echo = Echo()
    wait = RecordingWait()
    run_chat(
        _config(),
        question=None,
        interactive=True,
        rest=rest,
        wait=wait,
        prompt=prompt,
        echo=echo,
    )
    assert echo.out == ["one", "two"]
    assert [call.json_body["input"] for call in rest.calls] == [
        "first question",
        "follow up",
    ]
    assert "previous_response_id" not in rest.calls[0].json_body
    assert rest.calls[1].json_body["previous_response_id"] == "resp_a"
    assert wait.events == ["start", "stop", "start", "stop"]


def test_repl_keyboard_interrupt_during_ask_returns_to_prompt() -> None:
    class InterruptRest:
        def request(self, *args: object, **kwargs: object) -> object:
            raise KeyboardInterrupt

    lines = iter(["hello", "/quit"])

    def prompt(_label: str) -> str:
        return next(lines)

    echo = Echo()
    wait = RecordingWait()
    run_chat(
        _config(),
        question=None,
        interactive=True,
        rest=InterruptRest(),  # type: ignore[arg-type]
        wait=wait,
        prompt=prompt,
        echo=echo,
    )
    assert echo.out == []
    assert echo.err == [""]
    assert wait.events == ["start", "stop"]


def test_wait_indicator_starts_and_stops_on_empty_answer() -> None:
    rest = FakeRest().expect(
        "POST",
        "/openai/v1/responses",
        json_response(200, {"id": "resp_empty", "output_text": ""}),
    )
    wait = RecordingWait()
    echo = Echo()
    with pytest.raises(TalosError, match="empty text"):
        run_chat(
            _config(),
            question="hello",
            interactive=False,
            rest=rest,
            wait=wait,
            echo=echo,
        )
    assert wait.events == ["start", "stop"]
    assert echo.out == []


def test_wait_indicator_starts_and_stops_on_http_error() -> None:
    rest = FakeRest().expect(
        "POST",
        "/openai/v1/responses",
        json_response(503, {"error": {"message": "busy"}}),
    )
    wait = RecordingWait()
    with pytest.raises(TalosError, match="503"):
        run_chat(
            _config(),
            question="hello",
            interactive=False,
            rest=rest,
            wait=wait,
            echo=Echo(),
        )
    assert wait.events == ["start", "stop"]


def test_dry_run_does_not_start_wait() -> None:
    wait = RecordingWait()
    echo = Echo()
    run_chat(
        _config(dry_run=True),
        question="hello",
        interactive=False,
        rest=FakeRest(),
        wait=wait,
        echo=echo,
    )
    assert wait.events == []
    assert echo.out[0] == "dry-run chat"


def test_one_shot_stdout_is_only_the_answer() -> None:
    rest = FakeRest().expect(
        "POST",
        "/openai/v1/responses",
        json_response(200, _ok_body("just the answer")),
    )
    echo = Echo()
    run_chat(
        _config(),
        question="Q",
        interactive=False,
        rest=rest,
        wait=NullWait(),
        echo=echo,
    )
    assert echo.out == ["just the answer"]
    assert echo.err == []


def test_tty_wait_disabled_writes_nothing() -> None:
    stream = StringIO()
    indicator = TtyWaitIndicator(stream, enabled=False)
    indicator.start()
    indicator.stop()
    assert stream.getvalue() == ""


def test_tty_wait_enabled_writes_label_then_clears() -> None:
    stream = StringIO()
    indicator = TtyWaitIndicator(stream, enabled=True, interval=0.01)
    indicator.start()
    indicator._stop.wait(0.05)
    indicator.stop()
    text = stream.getvalue()
    assert WAIT_LABEL in text
    assert "\r" in text
