from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, TextIO

from talos.constants import DEFAULT_AGENT_NAME, FOUNDRY_SCOPE
from talos.errors import TalosError
from talos.rest import RestClient, raise_for_status

CHAT_TIMEOUT_SECONDS = 180.0
WAIT_LABEL = "Waiting for agent…"
_QUIT = frozenset({"/quit", "/exit", "quit", "exit"})
_SPINNER = "|/-\\"


@dataclass(frozen=True)
class ChatConfig:
    project_endpoint: str
    agent_name: str = DEFAULT_AGENT_NAME
    dry_run: bool = False
    timeout: float = CHAT_TIMEOUT_SECONDS


@dataclass(frozen=True)
class ChatTurn:
    text: str
    response_id: str


class WaitIndicator(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...


class NullWait:
    def start(self) -> None:
        return

    def stop(self) -> None:
        return


class TtyWaitIndicator:
    def __init__(
        self,
        stream: TextIO,
        *,
        enabled: bool | None = None,
        label: str = WAIT_LABEL,
        interval: float = 0.1,
    ) -> None:
        self._stream = stream
        self._enabled = stream.isatty() if enabled is None else enabled
        self._label = label
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self._enabled or self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.join(timeout=1.0)
        if self._enabled:
            width = len(self._label) + 4
            self._stream.write("\r" + " " * width + "\r")
            self._stream.flush()

    def _spin(self) -> None:
        index = 0
        while True:
            frame = _SPINNER[index % len(_SPINNER)]
            self._stream.write(f"\r{self._label} {frame}")
            self._stream.flush()
            index += 1
            if self._stop.wait(self._interval):
                return


def response_output_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    chunks: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunks)


def ask(
    rest: RestClient,
    config: ChatConfig,
    question: str,
    previous_response_id: str | None = None,
) -> ChatTurn:
    url = f"{config.project_endpoint.rstrip('/')}/openai/v1/responses"
    body: dict[str, Any] = {
        "input": question,
        "agent_reference": {
            "name": config.agent_name,
            "type": "agent_reference",
        },
    }
    if previous_response_id:
        body["previous_response_id"] = previous_response_id
    response = rest.request(
        "POST",
        url,
        scope=FOUNDRY_SCOPE,
        json_body=body,
        timeout=config.timeout,
    )
    raise_for_status(response, "agent responses")
    payload = response.json if isinstance(response.json, dict) else {}
    text = response_output_text(payload)
    if not text.strip():
        raise TalosError("agent responses returned empty text", exit_code=1)
    response_id = payload.get("id")
    return ChatTurn(
        text=text,
        response_id=str(response_id) if response_id else "",
    )


def run_chat(
    config: ChatConfig,
    question: str | None,
    *,
    interactive: bool,
    rest: RestClient | None = None,
    wait: WaitIndicator | None = None,
    prompt: Callable[[str], str] | None = None,
    echo: Callable[..., None] | None = None,
) -> None:
    if echo is None:
        echo = _default_echo
    if config.dry_run:
        echo("dry-run chat")
        echo(f"project: {config.project_endpoint}")
        echo(f"agent: {config.agent_name}")
        if question:
            echo(f"question: {question}")
        return
    if rest is None:
        from azure.identity import DefaultAzureCredential

        from talos.rest import RequestsRest

        rest = RequestsRest(DefaultAzureCredential())
    if wait is None:
        wait = TtyWaitIndicator(sys.stderr)
    if interactive:
        _run_repl(
            rest,
            config,
            wait=wait,
            prompt=prompt or _default_prompt,
            echo=echo,
        )
        return
    text = (question or "").strip()
    if not text:
        raise TalosError("question is required", exit_code=1)
    turn = _ask_waiting(rest, config, text, None, wait)
    echo(turn.text)


def _ask_waiting(
    rest: RestClient,
    config: ChatConfig,
    question: str,
    previous_response_id: str | None,
    wait: WaitIndicator,
) -> ChatTurn:
    wait.start()
    try:
        return ask(rest, config, question, previous_response_id)
    finally:
        wait.stop()


def _run_repl(
    rest: RestClient,
    config: ChatConfig,
    *,
    wait: WaitIndicator,
    prompt: Callable[[str], str],
    echo: Callable[..., None],
) -> None:
    previous_id: str | None = None
    while True:
        try:
            line = prompt("> ")
        except EOFError:
            return
        except KeyboardInterrupt:
            echo("", err=True)
            return
        question = line.strip()
        if not question:
            continue
        if question.lower() in _QUIT:
            return
        try:
            turn = _ask_waiting(rest, config, question, previous_id, wait)
        except TalosError as exc:
            echo(str(exc), err=True)
            continue
        echo(turn.text)
        if turn.response_id:
            previous_id = turn.response_id


def _default_echo(message: object = "", err: bool = False, **_: object) -> None:
    stream = sys.stderr if err else sys.stdout
    text = "" if message is None else str(message)
    stream.write(text if text.endswith("\n") else f"{text}\n")
    stream.flush()


def _default_prompt(label: str) -> str:
    sys.stderr.write(label)
    sys.stderr.flush()
    line = sys.stdin.readline()
    if line == "":
        raise EOFError
    return line.rstrip("\n")
