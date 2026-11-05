"""Roblox's public web APIs, for the names and pictures the log does not carry."""

import json
import logging
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

log = logging.getLogger(__name__)

USER_AGENT = "roserpc/0.1"
REQUEST_TIMEOUT = 10.0
# A failed lookup is retried after this long rather than on every poll.
RETRY_AFTER = 30.0
THUMBNAIL_SIZE = "512x512"
HEADSHOT_SIZE = "150x150"


@dataclass(frozen=True)
class Game:
    name: str
    creator: str
    verified: bool


@dataclass(frozen=True)
class User:
    name: str
    display_name: str


class RobloxApi:
    def __init__(self):
        self._cache = {}
        self._failed_at = {}

    def universe_for_place(self, place_id: int) -> int | None:
        def fetch():
            universe = self._get(f"https://apis.roblox.com/universes/v1/places/{place_id}/universe")
            return int(universe["universeId"])

        return self._cached(("universe", place_id), fetch)

    def game(self, universe_id: int) -> Game | None:
        def fetch():
            data = self._get("https://games.roblox.com/v1/games", universeIds=universe_id)["data"][0]
            creator = data["creator"]
            return Game(data["name"], creator["name"], bool(creator.get("hasVerifiedBadge")))

        return self._cached(("game", universe_id), fetch)

    def game_icon(self, universe_id: int) -> str | None:
        return self._cached(
            ("game_icon", universe_id),
            lambda: self._thumbnail("games/icons", universeIds=universe_id, size=THUMBNAIL_SIZE),
        )

    def asset_thumbnail(self, asset_id: int) -> str | None:
        return self._cached(
            ("asset", asset_id),
            lambda: self._thumbnail("assets", assetIds=asset_id, size=THUMBNAIL_SIZE),
        )

    def user(self, user_id: int) -> User | None:
        def fetch():
            data = self._get(f"https://users.roblox.com/v1/users/{user_id}")
            return User(data["name"], data["displayName"])

        return self._cached(("user", user_id), fetch)

    def headshot(self, user_id: int) -> str | None:
        return self._cached(
            ("headshot", user_id),
            lambda: self._thumbnail("users/avatar-headshot", userIds=user_id, size=HEADSHOT_SIZE),
        )

    def _thumbnail(self, endpoint: str, **query) -> str:
        query.update(format="Png", isCircular="false", returnPolicy="PlaceHolder")
        url = self._get(f"https://thumbnails.roblox.com/v1/{endpoint}", **query)["data"][0]["imageUrl"]
        if not url:
            # Still being rendered; the retry picks it up later.
            raise ValueError(f"no thumbnail yet for {endpoint} {query}")
        return url

    def _get(self, url: str, **query):
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return json.load(response)

    def _cached(self, key, fetch):
        if key in self._cache:
            return self._cache[key]
        failed_at = self._failed_at.get(key)
        if failed_at is not None and time.monotonic() - failed_at < RETRY_AFTER:
            return None
        try:
            value = fetch()
        except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
            log.warning("Roblox API lookup %s failed: %s", key, error)
            self._failed_at[key] = time.monotonic()
            return None
        self._cache[key] = value
        self._failed_at.pop(key, None)
        return value
