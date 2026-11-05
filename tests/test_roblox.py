import os
import plistlib
import tempfile
import unittest

from roserpc.roblox import (
    RobloxProcess,
    is_roblox_command,
    log_directories,
    runs_player_bundle,
)

RUNTIME = b"/home/u/.var/app/io.github.microlift.butter/data/butter/runners/rosemary-v0.5.0-official/Rosemary/bin/rosemary"


def command(*arguments: str) -> list[bytes]:
    return [argument.encode() for argument in arguments]


class PlayerDetectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.prefix = os.path.join(self.tmp.name, "bottles", "roblox", "prefix")
        self.applications = os.path.join(self.prefix, "root", "Applications")
        self.player = self.bundle("Roblox.app", "RobloxPlayer")
        self.studio = self.bundle("RobloxStudio.app", "RobloxStudio")
        self.env = {"ROSEMARY_PREFIX": self.prefix, "HOME": "/home/u"}

    def tearDown(self):
        self.tmp.cleanup()

    def bundle(self, name: str, executable: str) -> str:
        path = os.path.join(self.applications, name)
        os.makedirs(os.path.join(path, "Contents"))
        with open(os.path.join(path, "Contents", "Info.plist"), "wb") as info:
            plistlib.dump({"CFBundleExecutable": executable}, info, fmt=plistlib.FMT_BINARY)
        return path

    def test_player_named_by_its_executable_is_found(self):
        self.assertTrue(
            is_roblox_command(command("rosemary", "run", "--emulated", "/x/Roblox.app/Contents/MacOS/RobloxPlayer"))
        )
        self.assertFalse(is_roblox_command(command("rosemary", "run", "/x/RobloxPlayerInstaller")))

    def test_bundle_launched_by_butter_is_the_player(self):
        arguments = [RUNTIME, b"run", self.player.encode()]
        self.assertTrue(runs_player_bundle(arguments, self.env, "/home/u"))

    def test_bundle_named_by_its_guest_path_is_the_player(self):
        arguments = [RUNTIME, b"run", b"/Applications/Roblox.app/"]
        self.assertTrue(runs_player_bundle(arguments, self.env, "/home/u"))
        self.assertFalse(runs_player_bundle(arguments, {"ROSEMARY_PREFIX": "off"}, "/home/u"))

    def test_other_bundles_and_programs_are_not_the_player(self):
        self.assertFalse(runs_player_bundle([RUNTIME, b"run", self.studio.encode()], self.env, None))
        crash_handler = [
            RUNTIME,
            b"run",
            b"/Applications/Roblox.app/Contents/MacOS/RobloxCrashHandler",
            b"--no-rate-limit",
        ]
        self.assertFalse(runs_player_bundle(crash_handler, self.env, None))
        self.assertFalse(runs_player_bundle([RUNTIME, b"run", b"/missing/Roblox.app"], {}, None))

    def test_butters_keeper_is_not_the_player(self):
        keeper = [
            b"butter",
            b"--supervise",
            b"--log",
            b"/home/u/run.log",
            b"--",
            RUNTIME,
            b"run",
            self.player.encode(),
        ]
        self.assertFalse(runs_player_bundle(keeper, self.env, None))
        self.assertFalse(is_roblox_command(keeper))

    def test_logs_are_found_in_the_bottles_prefix(self):
        logs = os.path.join(self.prefix, "root", "Users", "u", "Library", "Logs", "Roblox")
        os.makedirs(logs)
        process = RobloxProcess(1, 0.0, self.env, "/home/u")
        self.assertEqual(log_directories(process), [logs])


if __name__ == "__main__":
    unittest.main()
