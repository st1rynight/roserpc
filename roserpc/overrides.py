"""Presence changes a game asks for by printing BloxstrapRPC messages.

Follows Bloxstrap's documented semantics: a missing field leaves the value
alone, "<reset>" restores the game's default, and a time of 0 clears it.
"""

MAX_TEXT = 128
RESET = "<reset>"


class _Unset:
    def __repr__(self):
        return "UNSET"


# Not overridden: the game's default stands. None means cleared.
UNSET = _Unset()


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _text(value, current):
    if not isinstance(value, str) or len(value) > MAX_TEXT:
        return current
    return UNSET if value == RESET else value


def _time(value, current):
    if not _is_number(value):
        return current
    return None if value == 0 else int(value)


class ImageOverride:
    def __init__(self):
        self.asset_id = UNSET
        self.text = UNSET

    def apply(self, data: dict) -> None:
        if data.get("clear") is True:
            self.asset_id = None
        elif data.get("reset") is True:
            self.asset_id = UNSET
            self.text = UNSET
        else:
            if _is_number(data.get("assetId")):
                self.asset_id = int(data["assetId"])
            if isinstance(data.get("hoverText"), str):
                self.text = data["hoverText"]


class Overrides:
    def __init__(self):
        self.details = UNSET
        self.state = UNSET
        self.start = UNSET
        self.end = UNSET
        self.large_image = ImageOverride()
        self.small_image = ImageOverride()

    def apply(self, data: dict) -> None:
        self.details = _text(data.get("details"), self.details)
        self.state = _text(data.get("state"), self.state)
        self.start = _time(data.get("timeStart"), self.start)
        self.end = _time(data.get("timeEnd"), self.end)
        if isinstance(data.get("largeImage"), dict):
            self.large_image.apply(data["largeImage"])
        if isinstance(data.get("smallImage"), dict):
            self.small_image.apply(data["smallImage"])
