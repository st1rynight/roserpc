"""Follow what the player is doing from the lines Roblox writes to its log."""

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from .overrides import Overrides

JOINING = re.compile(r"\[FLog::Output\] ! Joining game '(?P<job>[0-9A-Fa-f-]+)' place (?P<place>\d+) at ")
LOAD_TIME = "[FLog::GameJoinLoadTime] Report game_join_loadtime:"
LOAD_TIME_FIELD = re.compile(r"\b(?P<name>placeid|userid|universeid):(?P<value>\d+)")
JOIN_REQUEST = re.compile(r"\[FLog::GameJoinUtil\] GameJoinUtil::(?P<kind>joinGamePost\w+|initiateTeleport\w*)")
TELEPORT_MARKERS = ("GameJoinUtil::initiateTeleport", "UgcExperienceController: doTeleport")
LEAVING = "[FLog::SingleSurfaceApp] leaveUGCGameInternal"
# Also written when a teleport drops the old server, which is not a leave.
DISCONNECTED = "[FLog::Network] Time to disconnect replication data"
RPC_MESSAGE = re.compile(r"\[FLog::Output\] \[BloxstrapRPC\] (?P<json>.*)$")
RPC_SET_RICH_PRESENCE = "SetRichPresence"
LINE_TIME = re.compile(r"^(?P<time>\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?)Z,")


class ServerType(Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    RESERVED = "reserved"


def server_type_for(join_kind: str) -> ServerType:
    if "PrivateServer" in join_kind:
        return ServerType.PRIVATE
    if "ReservedServer" in join_kind:
        return ServerType.RESERVED
    return ServerType.PUBLIC


def line_time(line: str) -> float | None:
    match = LINE_TIME.match(line)
    if match is None:
        return None
    return datetime.fromisoformat(match["time"]).replace(tzinfo=timezone.utc).timestamp()


@dataclass
class Session:
    place_id: int
    job_id: str
    server_type: ServerType
    joined_at: float
    universe_id: int | None = None
    user_id: int | None = None
    overrides: Overrides = field(default_factory=Overrides)


class ActivityWatcher:
    def __init__(self):
        self.session: Session | None = None
        self.user_id: int | None = None
        self._next_server_type = ServerType.PUBLIC
        self._teleporting = False
        # The session a teleport left, so time in one universe keeps counting.
        self._previous: Session | None = None

    def feed(self, line: str) -> None:
        if match := JOIN_REQUEST.search(line):
            self._next_server_type = server_type_for(match["kind"])
        if self.session is not None and any(marker in line for marker in TELEPORT_MARKERS):
            self._teleporting = True

        if match := JOINING.search(line):
            self._join(line, int(match["place"]), match["job"])
        elif LOAD_TIME in line:
            self._loaded(line)
        elif LEAVING in line or (DISCONNECTED in line and not self._teleporting):
            self._leave()
        elif match := RPC_MESSAGE.search(line):
            self._rpc_message(match["json"])

    def _join(self, line: str, place_id: int, job_id: str) -> None:
        self._previous = self.session if self._teleporting else None
        self.session = Session(
            place_id=place_id,
            job_id=job_id,
            server_type=self._next_server_type,
            joined_at=line_time(line) or time.time(),
            user_id=self.user_id,
        )
        self._next_server_type = ServerType.PUBLIC
        self._teleporting = False

    def _loaded(self, line: str) -> None:
        fields = {m["name"]: int(m["value"]) for m in LOAD_TIME_FIELD.finditer(line)}
        if self.session is None or fields.get("placeid") != self.session.place_id:
            return
        if "userid" in fields:
            self.user_id = self.session.user_id = fields["userid"]
        if "universeid" in fields:
            self.session.universe_id = fields["universeid"]
            previous = self._previous
            if previous is not None and previous.universe_id == self.session.universe_id:
                self.session.joined_at = previous.joined_at
        self._previous = None

    def _leave(self) -> None:
        self.session = None
        self._previous = None
        self._teleporting = False

    def _rpc_message(self, text: str) -> None:
        if self.session is None:
            return
        try:
            message = json.loads(text)
        except ValueError:
            return
        if not isinstance(message, dict) or message.get("command") != RPC_SET_RICH_PRESENCE:
            return
        data = message.get("data")
        if isinstance(data, dict):
            self.session.overrides.apply(data)
