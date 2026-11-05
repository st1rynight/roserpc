import unittest

from roserpc.activity import ActivityWatcher, ServerType, line_time
from roserpc.api import Game, User
from roserpc.presence import ROBLOX_ICON, game_activity

PLACE = 5670218884
TELEPORT_PLACE = 111434027714006
UNIVERSE = 1998835206
USER = 1505161317
JOB = "6786919f-a252-4d83-8c2c-3c98b21f1009"
TELEPORT_JOB = "6e2219b4-2740-4cac-8aae-74a3d72a1d33"

STANDARD_JOIN = [
    "2026-11-05T08:02:43.685Z,6.685811,d5567800,6,Info [FLog::GameJoinUtil] GameJoinUtil::joinGamePostStandard: "
    'URL: https://gamejoin.roblox.com/v1/join-game BODY: {"placeId":5670218884}',
    f"2026-11-05T08:02:44.128Z,7.128855,ea710000,6 [FLog::Output] ! Joining game '{JOB}' place {PLACE} at 10.32.6.163",
    "2026-11-05T08:02:44.128Z,7.128879,ea710000,6 [FLog::GameJoinLoadTime] Report game_join_loadtime: "
    f"sid:b73291e5, clienttime:1793865764.69, join_time:0.46, referral_page:Home, placeid:{PLACE}, "
    f"userid:{USER}, universeid:{UNIVERSE}, ",
    "2026-11-05T08:02:44.611Z,7.611342,e9e00000,7 [FLog::Network] serverId: 128.116.54.33|64147",
]

RESERVED_TELEPORT = [
    "2026-11-05T08:02:48.999Z,11.999416,d5567800,6,Info [FLog::GameJoinUtil] "
    "GameJoinUtil::initiateTeleportToReservedServer: URL: https://gamejoin.roblox.com/v1/join-reserved-game",
    "2026-11-05T08:02:49.232Z,12.232841,e9e00000,7 [FLog::Network] Time to disconnect replication data: 0.258096",
    "2026-11-05T08:02:49.297Z,12.297005,e9e00000,6 [FLog::SessionTransitionFSM] Teleported.",
    f"2026-11-05T08:02:49.302Z,12.302341,e9e00000,6 [FLog::Output] ! Joining game '{TELEPORT_JOB}' "
    f"place {TELEPORT_PLACE} at 10.186.11.38",
    "2026-11-05T08:02:49.302Z,12.302341,e9e00000,6 [FLog::GameJoinLoadTime] Report game_join_loadtime: "
    f"sid:f672bfd6, clienttime:1793865769.86, join_time:0, referral_page:, placeid:{TELEPORT_PLACE}, "
    f"userid:{USER}, universeid:{UNIVERSE}, ",
]

LEAVE = "2026-11-05T08:03:29.026Z,52.026676,d5567800,6 [FLog::SingleSurfaceApp] leaveUGCGameInternal"


def rpc_line(json_text: str) -> str:
    return f"2026-11-05T08:02:50.000Z,13.0,d5567800,6 [FLog::Output] [BloxstrapRPC] {json_text}"


def watch(lines) -> ActivityWatcher:
    watcher = ActivityWatcher()
    for line in lines:
        watcher.feed(line)
    return watcher


class FakeApi:
    def universe_for_place(self, place_id):
        return UNIVERSE

    def game(self, universe_id):
        return Game("[🌳] item asylum", "JPX Studios", verified=True)

    def game_icon(self, universe_id):
        return "https://tr.rbxcdn.com/icon.png"

    def asset_thumbnail(self, asset_id):
        return f"https://tr.rbxcdn.com/asset-{asset_id}.png"

    def user(self, user_id):
        return User("88_Moose", "Mr_St1ry")

    def headshot(self, user_id):
        return "https://tr.rbxcdn.com/headshot.png"


def activity(watcher, show_account=False, show_buttons=True):
    return game_activity(watcher.session, FakeApi(), show_account=show_account, show_buttons=show_buttons)


class ActivityWatcherTests(unittest.TestCase):
    def test_joining_records_place_universe_and_join_time(self):
        session = watch(STANDARD_JOIN).session
        self.assertEqual(session.place_id, PLACE)
        self.assertEqual(session.job_id, JOB)
        self.assertEqual(session.universe_id, UNIVERSE)
        self.assertEqual(session.user_id, USER)
        self.assertIs(session.server_type, ServerType.PUBLIC)
        self.assertEqual(session.joined_at, line_time(STANDARD_JOIN[1]))

    def test_teleport_within_a_universe_keeps_the_join_time(self):
        session = watch(STANDARD_JOIN + RESERVED_TELEPORT).session
        self.assertEqual(session.place_id, TELEPORT_PLACE)
        self.assertIs(session.server_type, ServerType.RESERVED)
        self.assertEqual(session.joined_at, line_time(STANDARD_JOIN[1]))

    def test_disconnect_during_teleport_is_not_a_leave(self):
        watcher = watch(STANDARD_JOIN + RESERVED_TELEPORT[:2])
        self.assertIsNotNone(watcher.session)

    def test_disconnect_outside_teleport_is_a_leave(self):
        self.assertIsNone(watch(STANDARD_JOIN + [RESERVED_TELEPORT[1]]).session)

    def test_leaving_ends_the_session(self):
        self.assertIsNone(watch(STANDARD_JOIN + [LEAVE]).session)

    def test_private_server_join_is_private(self):
        private = STANDARD_JOIN[0].replace("joinGamePostStandard", "joinGamePostPrivateServer")
        session = watch([private] + STANDARD_JOIN[1:]).session
        self.assertIs(session.server_type, ServerType.PRIVATE)


class PresenceTests(unittest.TestCase):
    def test_public_game_shows_name_creator_icon_and_buttons(self):
        shown = activity(watch(STANDARD_JOIN))
        self.assertEqual(shown["details"], "[🌳] item asylum")
        self.assertEqual(shown["state"], "by JPX Studios ☑️")
        self.assertEqual(shown["timestamps"], {"start": int(line_time(STANDARD_JOIN[1]) * 1000)})
        self.assertEqual(shown["assets"]["large_image"], "https://tr.rbxcdn.com/icon.png")
        self.assertEqual(shown["assets"]["small_image"], ROBLOX_ICON)
        self.assertEqual([b["label"] for b in shown["buttons"]], ["Join server", "See game page"])
        self.assertIn(f"gameInstanceId={JOB}", shown["buttons"][0]["url"])

    def test_reserved_server_hides_join_button(self):
        shown = activity(watch(STANDARD_JOIN + RESERVED_TELEPORT))
        self.assertEqual(shown["state"], "In a reserved server")
        self.assertEqual([b["label"] for b in shown["buttons"]], ["See game page"])

    def test_account_replaces_small_image(self):
        shown = activity(watch(STANDARD_JOIN), show_account=True)
        self.assertEqual(shown["assets"]["small_image"], "https://tr.rbxcdn.com/headshot.png")
        self.assertEqual(shown["assets"]["small_text"], "Playing on Mr_St1ry (@88_Moose)")

    def test_game_rpc_message_overrides_and_resets(self):
        message = (
            '{"command":"SetRichPresence","data":{"details":"Round 3","state":"12 players",'
            '"timeEnd":1793866000,"largeImage":{"assetId":42,"hoverText":"Lobby"}}}'
        )
        watcher = watch(STANDARD_JOIN + [rpc_line(message)])
        shown = activity(watcher)
        self.assertEqual(shown["details"], "Round 3")
        self.assertEqual(shown["state"], "12 players")
        self.assertEqual(shown["timestamps"]["end"], 1793866000 * 1000)
        self.assertEqual(shown["assets"]["large_image"], "https://tr.rbxcdn.com/asset-42.png")
        self.assertEqual(shown["assets"]["large_text"], "Lobby")

        watcher.feed(rpc_line('{"command":"SetRichPresence","data":{"details":"<reset>","timeStart":0}}'))
        shown = activity(watcher)
        self.assertEqual(shown["details"], "[🌳] item asylum")
        self.assertNotIn("start", shown["timestamps"])

    def test_one_character_text_is_padded_for_discord(self):
        message = '{"command":"SetRichPresence","data":{"state":"x"}}'
        shown = activity(watch(STANDARD_JOIN + [rpc_line(message)]))
        self.assertGreaterEqual(len(shown["state"]), 2)


if __name__ == "__main__":
    unittest.main()
