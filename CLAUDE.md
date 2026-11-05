# CLAUDE.md

Guidance for AI agents working in this repository.

## What this is

roserpc shows Discord Rich Presence for Roblox running under
[Rosemary](https://github.com/microlift/rosemary), the macOS compatibility layer. It is a separate
program: it observes Rosemary from the outside and never changes it. Do not propose edits to
Rosemary to make roserpc work. Find what Rosemary already exposes: process arguments, the prefix
filesystem, or the environment.

Python 3.10+, standard library only. Keep it that way; a user should be able to clone and run it
without installing anything else.

## Run and test

```sh
bin/roserpc -v                                   # run from the checkout (sets PYTHONPATH)
python3 -m roserpc -v                            # same, from the repo root
python3 -m unittest discover -s tests -v         # all tests
python3 -m unittest tests.test_activity -v       # one module
```

## How it works

One polling loop (`__main__.RoseRpc.tick`, every `POLL_INTERVAL` seconds):

```
find_roblox() -> newest_player_log() -> LogTail -> ActivityWatcher.feed(line)
    -> game_activity()/menu_activity() -> RoseRpc._show() -> DiscordClient.set_activity()
```

| Module | Role |
|---|---|
| `roblox.py` | Finds the player process. On Linux it reads `/proc`; elsewhere it uses `ps`. It works out the log directories from the process's own `ROSEMARY_PREFIX` / `ROSEMARY_PREFIX_HOME` / `XDG_DATA_HOME`, picks the newest `*_Player_*_last.log`, and tails it. |
| `activity.py` | `ActivityWatcher`: a state machine over Roblox log lines that produces the current `Session` (place, job, universe, user, server type, join time). |
| `overrides.py` | Bloxstrap's `BloxstrapRPC` `SetRichPresence` semantics. `UNSET` means "the game's default", `None` means cleared, and `"<reset>"` restores the default. |
| `presence.py` | Builds the Discord activity dict from a `Session`, the Roblox APIs and the overrides. It drops empty fields and pads 1-character text, since Discord rejects both. |
| `api.py` | Roblox web APIs (games, thumbnails, users, universe lookup). Results are cached; a failure is retried after `RETRY_AFTER`. |
| `discord.py` | Discord's IPC protocol: `<op:u32le><len:u32le><json>` frames, handshake, `SET_ACTIVITY` replies matched by nonce, and `PING`/`PONG`. |

### Facts the code depends on

These were established against real logs and a real Discord client. Re-check them against a real
session before changing anything that relies on them.

* **Process.** Rosemary execs guests as `<runtime> run [--emulated] <path> ...`, so the player is
  an argument whose basename is `RobloxPlayer`. `RobloxPlayerInstaller` must not match.
* **Logs.** By default they live in `<prefix>/root/Users/<name>/Library/Logs/Roblox`. One player
  log is written per launch, and joining several games in one launch appends to the same log.
  Ignore `*CrashHandler*` logs.
* **Log markers:**
  * `[FLog::Output] ! Joining game '<job>' place <id> at <ip>` starts a session.
  * The `[FLog::GameJoinLoadTime]` line right after it carries `placeid`, `userid` and
    `universeid`.
  * `GameJoinUtil::joinGamePost{Standard,PrivateServer}` and
    `GameJoinUtil::initiateTeleportToReservedServer` give the next session's server type.
  * `leaveUGCGameInternal` is a leave.
  * `Time to disconnect replication data` is a leave *unless* a teleport is in progress
    (`initiateTeleport` / `doTeleport` was seen).
  * A teleport within the same universe keeps the original join time.
* **Discord throttling.** Discord acknowledges every `SET_ACTIVITY` but only displays about one
  per 15 seconds and silently drops the rest. `MIN_UPDATE_INTERVAL = 15` coalesces changes so the
  last state is always the one sent. Lowering it brings back the "presence froze after switching
  games" bug. Discord's `~/.config/discord/logs/renderer_js.log` shows each received message.
* **Clearing.** Closing the IPC connection clears the activity, so roserpc disconnects instead of
  sending a null activity, and leaves Discord alone while Roblox is closed.
* **Default client ID.** It is Bloxstrap's public application (named "Roblox", with a `roblox`
  art asset).

## Conventions

* Accuracy over approximation. If something has to be inaccurate, mark it with a
  `FIXME (ACCURACY): ...` comment that says why (see `roblox._find_with_ps`).
* Name constants instead of using magic numbers or strings; log markers live at the top of
  `activity.py`.
* Comments are short, ASCII and explain *why*.
* Tests sit in `tests/`, named for observable behaviour (`test_leaving_ends_the_session`). Use log
  lines copied from real Roblox logs, with user-identifying values trimmed. No network access in
  tests: use a fake API (`tests/test_activity.py`) and a socketpair in place of Discord
  (`tests/test_discord.py`).
* To debug a real session, replay its log through `RoseRpc.tick` with a fake clock and a recording
  Discord stub. That shows exactly what would have been sent, and when, without touching anyone's
  Discord.
* Commits use imperative, scoped messages (`activity: handle reserved-server teleports`). Never
  list an AI agent, model or tool as a co-author.
