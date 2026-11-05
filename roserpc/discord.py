"""Discord's local RPC protocol, spoken over the client's IPC socket."""

import json
import os
import socket
import struct
import uuid

OP_HANDSHAKE = 0
OP_FRAME = 1
OP_CLOSE = 2
OP_PING = 3
OP_PONG = 4

RPC_VERSION = 1
HEADER = struct.Struct("<II")
MAX_SOCKET_INDEX = 10
IO_TIMEOUT = 5.0

# Sandboxed clients (Flatpak, Snap, Vesktop) put the socket one level down.
SANDBOX_SUBDIRS = (
    "",
    "app/com.discordapp.Discord",
    "app/com.discordapp.DiscordCanary",
    "app/com.discordapp.DiscordPTB",
    "app/dev.vencord.Vesktop",
    ".flatpak/dev.vencord.Vesktop/xdg-run",
    "snap.discord",
    "snap.discord-canary",
)


class DiscordError(Exception):
    """Discord refused a request; the connection itself is still usable."""


class Disconnected(Exception):
    """There is no connection; one has to be made before the next request."""


def socket_paths():
    bases = []
    for variable in ("XDG_RUNTIME_DIR", "TMPDIR", "TMP", "TEMP"):
        value = os.environ.get(variable)
        if value and value not in bases:
            bases.append(value)
    # The Linux client under FreeBSD's Linux compatibility layer sees
    # /compat/linux/tmp as its /tmp.
    for fallback in ("/tmp", "/compat/linux/tmp"):
        if fallback not in bases:
            bases.append(fallback)
    for index in range(MAX_SOCKET_INDEX):
        for base in bases:
            for subdir in SANDBOX_SUBDIRS:
                yield os.path.join(base, subdir, f"discord-ipc-{index}")


class DiscordClient:
    def __init__(self, client_id: str):
        self.client_id = client_id
        self._sock = None

    @property
    def connected(self) -> bool:
        return self._sock is not None

    def connect(self) -> dict:
        """Connect to the first Discord client that answers; return its user."""
        for path in socket_paths():
            if not os.path.exists(path):
                continue
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(IO_TIMEOUT)
            try:
                sock.connect(path)
            except OSError:
                sock.close()
                continue
            self._sock = sock
            try:
                self._send(OP_HANDSHAKE, {"v": RPC_VERSION, "client_id": self.client_id})
                op, payload = self._recv()
            except Disconnected:
                continue
            if op == OP_CLOSE:
                self.close()
                raise DiscordError(payload.get("message", "handshake rejected"))
            if payload.get("evt") == "READY":
                return payload.get("data", {}).get("user", {})
            self.close()
        raise Disconnected("no Discord client is listening")

    def set_activity(self, activity: dict | None) -> None:
        nonce = str(uuid.uuid4())
        args = {"pid": os.getpid(), "activity": activity}
        self._send(OP_FRAME, {"cmd": "SET_ACTIVITY", "args": args, "nonce": nonce})
        while True:
            op, payload = self._recv()
            if op == OP_CLOSE:
                self.close()
                raise Disconnected(payload.get("message", "Discord closed the connection"))
            if payload.get("nonce") != nonce:
                continue
            if payload.get("evt") == "ERROR":
                raise DiscordError(payload.get("data", {}).get("message", "unknown error"))
            return

    def close(self) -> None:
        """Disconnect; Discord drops the activity of a closed connection."""
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _send(self, op: int, payload: dict) -> None:
        if self._sock is None:
            raise Disconnected("not connected")
        body = json.dumps(payload, separators=(",", ":")).encode()
        try:
            self._sock.sendall(HEADER.pack(op, len(body)) + body)
        except OSError as error:
            self.close()
            raise Disconnected(str(error)) from error

    def _recv(self) -> tuple[int, dict]:
        while True:
            op, length = HEADER.unpack(self._read(HEADER.size))
            body = self._read(length)
            try:
                payload = json.loads(body) if body else {}
            except ValueError as error:
                self.close()
                raise Disconnected("malformed frame from Discord") from error
            if not isinstance(payload, dict):
                payload = {}
            if op == OP_PING:
                self._send(OP_PONG, payload)
                continue
            return op, payload

    def _read(self, size: int) -> bytes:
        buffer = bytearray()
        while len(buffer) < size:
            if self._sock is None:
                raise Disconnected("not connected")
            try:
                chunk = self._sock.recv(size - len(buffer))
            except OSError as error:
                self.close()
                raise Disconnected(str(error)) from error
            if not chunk:
                self.close()
                raise Disconnected("Discord closed the connection")
            buffer += chunk
        return bytes(buffer)
