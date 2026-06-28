"""TCP IPC между host (агент) и input (stdin-клиент)."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Literal

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
CONNECT_RETRIES = 5
CONNECT_RETRY_DELAY_SEC = 1.0

SourceKind = Literal["user", "scheduler"]


@dataclass(frozen=True)
class InboxItem:
    source: SourceKind
    text: str


@dataclass
class HostState:
    inbox: asyncio.Queue[InboxItem] = field(default_factory=asyncio.Queue)
    busy: bool = False


def encode_message(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")


def decode_message(raw: bytes) -> dict[str, Any]:
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("message must be a JSON object")
    return data


async def enqueue_item(state: HostState, item: InboxItem) -> None:
    if state.busy:
        pending = state.inbox.qsize() + 1
        print(f"[host] queued {item.source} ({pending} pending)", flush=True)
    await state.inbox.put(item)


async def send_ack(writer: asyncio.StreamWriter, *, queued: bool, pending: int) -> None:
    writer.write(
        encode_message({"type": "ack", "queued": queued, "pending": pending})
    )
    await writer.drain()


class HostServer:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        state: HostState,
    ) -> None:
        self._host = host
        self._port = port
        self._state = state
        self._server: asyncio.Server | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_client,
            self._host,
            self._port,
        )
        sockets = self._server.sockets or []
        if sockets:
            host, port = sockets[0].getsockname()[:2]
            print(f"[host] listening on {host}:{port}", flush=True)

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        peer = writer.get_extra_info("peername")
        print(f"[host] input connected {peer}", flush=True)
        try:
            while True:
                raw = await reader.readline()
                if not raw:
                    break
                try:
                    message = decode_message(raw)
                except (json.JSONDecodeError, ValueError) as exc:
                    print(f"[host] bad message from input: {exc}", flush=True)
                    continue

                msg_type = message.get("type")
                if msg_type == "quit":
                    break
                if msg_type != "user":
                    print(f"[host] unknown message type: {msg_type!r}", flush=True)
                    continue

                text = str(message.get("text") or "").strip()
                if not text:
                    await send_ack(
                        writer,
                        queued=False,
                        pending=self._state.inbox.qsize(),
                    )
                    continue

                await enqueue_item(self._state, InboxItem("user", text))
                await send_ack(
                    writer,
                    queued=True,
                    pending=self._state.inbox.qsize(),
                )
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass
            print(f"[host] input disconnected {peer}", flush=True)


class InputClient:
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        self._reader = reader
        self._writer = writer

    @classmethod
    async def connect(
        cls,
        *,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
    ) -> InputClient:
        last_exc: OSError | None = None
        for attempt in range(1, CONNECT_RETRIES + 1):
            try:
                reader, writer = await asyncio.open_connection(host, port)
                return cls(reader, writer)
            except OSError as exc:
                last_exc = exc
                if attempt < CONNECT_RETRIES:
                    await asyncio.sleep(CONNECT_RETRY_DELAY_SEC)
        raise ConnectionError(
            f"не удалось подключиться к host {host}:{port} "
            f"({last_exc}) — запустите `python main.py host`"
        ) from last_exc

    async def close(self) -> None:
        self._writer.close()
        try:
            await self._writer.wait_closed()
        except ConnectionError:
            pass

    async def send_quit(self) -> None:
        self._writer.write(encode_message({"type": "quit"}))
        await self._writer.drain()

    async def send_user(self, text: str) -> dict[str, Any]:
        self._writer.write(encode_message({"type": "user", "text": text}))
        await self._writer.drain()
        raw = await self._reader.readline()
        if not raw:
            raise ConnectionError("host closed connection")
        ack = decode_message(raw)
        return ack

    async def __aenter__(self) -> InputClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()
