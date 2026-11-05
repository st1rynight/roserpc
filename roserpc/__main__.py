"""roserpc: show the Roblox game you're playing under Rosemary on Discord."""

import argparse
import logging
import os
import signal
import sys
import time

from .activity import ActivityWatcher
from .api import RobloxApi
from .discord import DiscordClient, DiscordError, Disconnected
from .presence import game_activity, menu_activity
from .roblox import LogTail, find_roblox, log_directories, newest_player_log

log = logging.getLogger("roserpc")

# The public application Bloxstrap uses; Discord shows it as "Roblox".
DEFAULT_CLIENT_ID = "1005469189907173486"
POLL_INTERVAL = 2.0
DISCORD_RETRY = 15.0
# Discord acknowledges every update but only displays one per ~15 seconds,
# silently dropping the rest; changes in between are coalesced into the next.
MIN_UPDATE_INTERVAL = 15.0

_NOT_SENT = object()


class RoseRpc:
    def __init__(self, options: argparse.Namespace):
        self.options = options
        self.discord = DiscordClient(options.client_id)
        self.api = RobloxApi()
        self.tail: LogTail | None = None
        self.watcher: ActivityWatcher | None = None
        self.shown = None
        self.last_update = -MIN_UPDATE_INTERVAL
        self.next_connect = 0.0
        self.running_pid: int | None = None

    def run(self) -> None:
        while True:
            self.tick()
            time.sleep(POLL_INTERVAL)

    def tick(self) -> None:
        processes = find_roblox()
        if not processes:
            if self.running_pid is not None:
                log.info("Roblox exited")
                self.running_pid = None
            self._follow(None)
            self._show(None)
            return

        first = min(processes, key=lambda p: p.started)
        if self.running_pid != first.pid:
            log.info("Roblox is running (pid %d)", first.pid)
            self.running_pid = first.pid
        directories = [self.options.log_dir] if self.options.log_dir else log_directories(first)
        self._follow(newest_player_log(directories, first.started))
        if self.tail is not None:
            for line in self.tail.read_lines():
                self.watcher.feed(line)
        self._show(self._wanted_activity(first.started))

    def shutdown(self) -> None:
        self._follow(None)
        self.discord.close()

    def _wanted_activity(self, launched_at: float) -> dict | None:
        session = self.watcher.session if self.watcher else None
        if session is not None:
            return game_activity(
                session,
                self.api,
                show_account=self.options.show_account,
                show_buttons=not self.options.no_buttons,
            )
        return None if self.options.hide_menu else menu_activity(launched_at)

    def _follow(self, path: str | None) -> None:
        if self.tail is not None and self.tail.path == path:
            return
        if self.tail is not None:
            self.tail.close()
        self.tail = self.watcher = None
        if path is None:
            return
        try:
            self.tail = LogTail(path)
        except OSError as error:
            log.warning("cannot read %s: %s", path, error)
            return
        self.watcher = ActivityWatcher()
        log.info("following %s", path)

    def _show(self, activity: dict | None) -> None:
        if activity == self.shown:
            return
        if activity is None:
            # Closing the connection clears the activity, and leaves Discord
            # alone while Roblox is not running.
            self.discord.close()
            self.shown = None
            log.info("cleared presence")
            return
        now = time.monotonic()
        if not self.discord.connected:
            if now < self.next_connect:
                return
            try:
                user = self.discord.connect()
            except (Disconnected, DiscordError) as error:
                log.warning("cannot reach Discord: %s; retrying in %ds", error, DISCORD_RETRY)
                self.next_connect = now + DISCORD_RETRY
                return
            log.info("connected to Discord as %s", user.get("username", "?"))
            self.shown = None
        if now - self.last_update < MIN_UPDATE_INTERVAL:
            return
        self.last_update = now
        try:
            self.discord.set_activity(activity)
        except Disconnected as error:
            log.warning("lost Discord: %s", error)
            self.shown = None
            return
        except DiscordError as error:
            # Remembered anyway, so a rejected activity is not resent every poll.
            log.warning("Discord rejected the activity: %s", error)
        self.shown = activity
        log.info("presence: %s", " - ".join(filter(None, (activity.get("details"), activity.get("state")))))


def parse_options(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="roserpc", description=__doc__)
    parser.add_argument(
        "--client-id",
        default=os.environ.get("ROSERPC_CLIENT_ID", DEFAULT_CLIENT_ID),
        help="Discord application ID; its name is what Discord shows after 'Playing'",
    )
    parser.add_argument("--log-dir", help="Roblox log directory, if not found automatically")
    parser.add_argument(
        "--show-account", action="store_true", help="show your Roblox avatar and username"
    )
    parser.add_argument("--no-buttons", action="store_true", help="leave out the Join server / game page buttons")
    parser.add_argument("--hide-menu", action="store_true", help="show nothing while in the Roblox menus")
    parser.add_argument("-v", "--verbose", action="store_true", help="log debugging detail")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    options = parse_options(argv)
    logging.basicConfig(
        level=logging.DEBUG if options.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    app = RoseRpc(options)
    log.info("waiting for Roblox")
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        app.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
