"""Find a Roblox player running under Rosemary, and the log it is writing."""

import glob
import os
import plistlib
import subprocess
import sys
import time
from dataclasses import dataclass, field
from xml.parsers.expat import ExpatError

# Rosemary runs a guest as `rosemary run [--emulated] <path> ...`, so the
# player shows up as an argument, not as the process name. Butter passes the
# bundle instead (`rosemary run .../Roblox.app`), so a bundle whose
# executable is the player counts too.
PLAYER_NAME = "RobloxPlayer"
PLAYER_EXECUTABLE = PLAYER_NAME.encode()
RUN_COMMAND = b"run"
OPTION_MARKER = b"-"
APP_BUNDLE_SUFFIX = b".app"
BUNDLE_INFO = os.path.join("Contents", "Info.plist")
BUNDLE_EXECUTABLE_KEY = "CFBundleExecutable"
GUEST_ROOT = "root"
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


def bundle_target(arguments: list[bytes]) -> bytes | None:
    """The `.app` a `rosemary run [options] <bundle>` command line runs.
    Only the runtime's own `run` counts, not a wrapper naming it later."""
    if len(arguments) < 2 or arguments[1] != RUN_COMMAND:
        return None
    for argument in arguments[2:]:
        if not argument.startswith(OPTION_MARKER):
            target = argument.rstrip(b"/")
            return target if target.endswith(APP_BUNDLE_SUFFIX) else None
    return None


def _bundle_executable(bundle: str) -> str | None:
    try:
        with open(os.path.join(bundle, BUNDLE_INFO), "rb") as info:
            executable = plistlib.load(info).get(BUNDLE_EXECUTABLE_KEY)
    except (OSError, ValueError, ExpatError, AttributeError):
        return None
    return executable if isinstance(executable, str) else None


def runs_player_bundle(arguments: list[bytes], environ: dict, cwd: str | None) -> bool:
    """Whether the command line runs a bundle whose executable is the player.
    The bundle may be named by its host path or by its path in the guest."""
    target = bundle_target(arguments)
    if target is None:
        return False
    target = os.fsdecode(target)
    candidates = []
    if os.path.isabs(target):
        candidates.append(target)
        prefix = rosemary_prefix(environ, cwd)
        if prefix:
            candidates.append(os.path.join(prefix, GUEST_ROOT, target.lstrip("/")))
    elif cwd:
        candidates.append(os.path.join(cwd, target))
    return any(_bundle_executable(bundle) == PLAYER_NAME for bundle in candidates)


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
            named = is_roblox_command(arguments)
            if not named and bundle_target(arguments) is None:
                continue
            started = _start_time(pid, boot_time)
            try:
                cwd = os.readlink(f"/proc/{pid}/cwd")
            except OSError:
                cwd = None
        except (OSError, ValueError, IndexError):
            continue
        environ = _environ(pid)
        if named or runs_player_bundle(arguments, environ, cwd):
            found.append(RobloxProcess(pid, started, environ, cwd))
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
        if is_roblox_command(arguments) or runs_player_bundle(arguments, dict(os.environ), None):
            found.append(RobloxProcess(int(fields[0]), now - int(fields[1]), {}, None))
    return found


def find_roblox() -> list[RobloxProcess]:
    if sys.platform.startswith("linux"):
        return _find_in_proc()
    return _find_with_ps()


def rosemary_prefix(env: dict, cwd: str | None) -> str | None:
    """The prefix a process with this environment and directory uses, or
    None when ROSEMARY_PREFIX=off."""
    prefix = env.get("ROSEMARY_PREFIX")
    if prefix == PREFIX_DISABLED:
        return None
    if not prefix:
        home = env.get("HOME") or os.path.expanduser("~")
        data_home = env.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
        prefix = os.path.join(data_home, DEFAULT_PREFIX)
    prefix = os.path.expanduser(prefix)
    if not os.path.isabs(prefix) and cwd:
        prefix = os.path.join(cwd, prefix)
    return prefix


def log_directories(process: RobloxProcess | None) -> list[str]:
    """Where the player's logs can be, following the process's Rosemary settings."""
    env = (process.environ if process else None) or os.environ
    home = env.get("HOME") or os.path.expanduser("~")
    candidates = []
    prefix = rosemary_prefix(env, process.cwd if process else None)
    if prefix is not None:
        users = os.path.join(glob.escape(prefix), GUEST_ROOT, "Users", "*", GUEST_LOGS)
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
