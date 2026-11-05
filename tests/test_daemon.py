import unittest
from unittest import mock

import roserpc.__main__ as daemon


class RecordingDiscord:
    connected = False

    def __init__(self):
        self.sent = []

    def connect(self):
        self.connected = True
        return {}

    def set_activity(self, activity):
        self.sent.append(activity)

    def close(self):
        self.connected = False


class ShowTests(unittest.TestCase):
    def setUp(self):
        self.clock = 1000.0
        patcher = mock.patch.object(daemon.time, "monotonic", lambda: self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.app = daemon.RoseRpc(daemon.parse_options([]))
        self.app.discord = RecordingDiscord()

    def test_changes_within_the_interval_are_coalesced_into_the_latest(self):
        first, menu, second = {"details": "First"}, {"details": "In the menus"}, {"details": "Second"}
        self.app._show(first)
        self.clock += 2
        self.app._show(menu)
        self.clock += 2
        self.app._show(second)
        self.assertEqual(self.app.discord.sent, [first])

        self.clock += daemon.MIN_UPDATE_INTERVAL
        self.app._show(second)
        self.assertEqual(self.app.discord.sent, [first, second])


if __name__ == "__main__":
    unittest.main()
