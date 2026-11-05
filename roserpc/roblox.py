"""Find a Roblox player running under Rosemary, and the log it is writing."""

import glob
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field

# Rosemary runs a guest as `rosemary run [--emulated] <path> ...`, so the
# player shows up as an argument, not as the process name.
PLAYER_EXECUTABLE = b"RobloxPlayer"
PLAYER_LOG_PATTERN = "*_Player_*_last.log"
CRASH_HANDLER_MARKER = "CrashHandler"
GUEST_LOGS = os.path.join("Library", "Logs", "Roblox")
DEFAULT_PREFIX = os.path.join("rosemary", "prefixes", "default")
PREFIX_DISABLED = "off"
# A log last written before the player started belongs to an earlier run.
LOG_START_SLACK = 10.0
# Field 22 of /proc/<pid>/stat, counted from the field after the command name.
STAT_STARTTIME_INDEX = 19
# pid, seconds since start, full arguments; understood by FreeBSD and procps.
PS_COMMAND = ("ps", "-axww", "-o", "pid=,etimes=,args=")


@dataclass(frozen=True)
class RobloxProcess:
    pid: int
    started: float
    environ: dict = field(compare=False)
    cwd: str | None


def _boot_time() -> float:
    with open("/proc/stat") as stat:
        for line in stat:
            if line.startswith("btime "):
                return float(line.split()[1])
    return 0.0


def _start_time(pid: int, boot_time: float) -> float:
    with open(f"/proc/{pid}/stat") as stat:
        text = stat.read()
    # The command name may itself contain spaces and parentheses.
    fields = text[text.rindex(")") + 2 :].split()
    ticks = int(fields[STAT_STARTTIME_INDEX])
    return boot_time + ticks / os.sysconf("SC_CLK_TCK")


def _environ(pid: int) -> dict:
    try:
        with open(f"/proc/{pid}/environ", "rb") as environ:
            entries = environ.read().split(b"\0")
    except OSError:
        return {}
    result = {}
    for entry in entries:
        name, sep, value = entry.partition(b"=")
        if sep:
            result[name.decode(errors="replace")] = value.decode(errors="replace")
    return result


def is_roblox_command(arguments: list[bytes]) -> bool:
    return any(os.path.basename(argument) == PLAYER_EXECUTABLE for argument in arguments)


def _find_in_proc() -> list[RobloxProcess]:
    boot_time = _boot_time()
    found = []
    for entry in os.scandir("/proc"):
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as cmdline:
                arguments = [a for a in cmdline.read().split(b"\0") if a]
            if not is_roblox_command(arguments):
                continue
            started = _start_time(pid, boot_time)
            try:
                cwd = os.readlink(f"/proc/{pid}/cwd")
            except OSError:
                cwd = None
        except (OSError, ValueError, IndexError):
            continue
        found.append(RobloxProcess(pid, started, _environ(pid), cwd))
    return found


def _find_with_ps() -> list[RobloxProcess]:
    """For hosts without Linux's /proc, such as FreeBSD.

    FIXME (ACCURACY): ps joins arguments with spaces, so a path containing
    spaces is split; only its last component is matched, which still works.
    The process's environment and directory are unknown, so roserpc's own
    Rosemary settings stand in for them.
    """
    try:
        listing = subprocess.run(PS_COMMAND, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    now = time.time()
    found = []
    for line in listing.splitlines():
        fields = line.split(None, 2)
        if len(fields) < 3 or not fields[0].isdigit() or not fields[1].isdigit():
            continue
        arguments = [argument.encode() for argument in fields[2].split()]
        if is_roblox_command(arguments):
            found.append(RobloxProcess(int(fields[0]), now - int(fields[1]), {}, None))
    return found


def find_roblox() -> list[RobloxProcess]:
    if sys.platform.startswith("linux"):
        return _find_in_proc()
    return _find_with_ps()


def log_directories(process: RobloxProcess | None) -> list[str]:
    """Where the player's logs can be, following the process's Rosemary settings."""
    env = (process.environ if process else None) or os.environ
    home = env.get("HOME") or os.path.expanduser("~")
    candidates = []
    prefix = env.get("ROSEMARY_PREFIX")
    if prefix != PREFIX_DISABLED:
        if not prefix:
            data_home = env.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
            prefix = os.path.join(data_home, DEFAULT_PREFIX)
        prefix = os.path.expanduser(prefix)
        if not os.path.isabs(prefix) and process and process.cwd:
            prefix = os.path.join(process.cwd, prefix)
        users = os.path.join(glob.escape(prefix), "root", "Users", "*", GUEST_LOGS)
        candidates.extend(sorted(glob.glob(users)))
    # ROSEMARY_PREFIX=off, or ROSEMARY_PREFIX_HOME=host, keeps the home on the host.
    candidates.append(os.path.join(home, GUEST_LOGS))
    return [d for d in dict.fromkeys(candidates) if os.path.isdir(d)]


def newest_player_log(directories: list[str], started: float) -> str | None:
    newest, newest_mtime = None, started - LOG_START_SLACK
    for directory in directories:
        for path in glob.glob(os.path.join(glob.escape(directory), PLAYER_LOG_PATTERN)):
            if CRASH_HANDLER_MARKER in os.path.basename(path):
                continue
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if mtime >= newest_mtime:
                newest, newest_mtime = path, mtime
    return newest


class LogTail:
    """Hands out the complete lines appended to a file since the last call."""

    def __init__(self, path: str):
        self.path = path
        self._file = open(path, "rb")
        self._partial = b""

    def read_lines(self) -> list[str]:
        data = self._file.read()
        if not data:
            return []
        lines = (self._partial + data).split(b"\n")
        self._partial = lines.pop()
        return [line.decode("utf-8", errors="replace").rstrip("\r") for line in lines]

    def close(self) -> None:
        self._file.close()
