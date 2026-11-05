"""Turn what the player is doing into a Discord activity."""

from .activity import ServerType, Session
from .api import RobloxApi
from .overrides import UNSET, ImageOverride

# An image uploaded to the Discord application under this key.
ROBLOX_ICON = "roblox"
ROBLOX_NAME = "Roblox"
MAX_TEXT = 128
MIN_TEXT = 2
# Discord rejects shorter strings; Braille blanks pad without showing.
TEXT_PADDING = "⠀"
VERIFIED_BADGE = " ☑️"
MILLISECONDS = 1000


def _discord_text(text: str | None) -> str | None:
    if not text:
        return None
    if len(text) < MIN_TEXT:
        text += TEXT_PADDING * MIN_TEXT
    return text[:MAX_TEXT]


def _milliseconds(seconds: float | None) -> int | None:
    return None if seconds is None else int(seconds * MILLISECONDS)


def _activity(details, state, start, end, large, small, buttons=None) -> dict:
    """Assemble an activity, leaving out what is empty, which Discord rejects."""
    activity = {}
    if text := _discord_text(details):
        activity["details"] = text
    if text := _discord_text(state):
        activity["state"] = text
    timestamps = {k: v for k, v in (("start", start), ("end", end)) if v is not None}
    if timestamps:
        activity["timestamps"] = timestamps
    assets = {}
    for prefix, (key, text) in (("large", large), ("small", small)):
        if key:
            assets[f"{prefix}_image"] = key
            if text := _discord_text(text):
                assets[f"{prefix}_text"] = text
    if assets:
        activity["assets"] = assets
    if buttons:
        activity["buttons"] = buttons
    return activity


def menu_activity(launched_at: float) -> dict:
    return _activity(
        details="In the menus",
        state=None,
        start=_milliseconds(launched_at),
        end=None,
        large=(ROBLOX_ICON, ROBLOX_NAME),
        small=(None, None),
    )


def _image(override: ImageOverride, key: str | None, text: str | None, api: RobloxApi):
    if override.asset_id is None:
        key = None
    elif override.asset_id is not UNSET:
        key = api.asset_thumbnail(override.asset_id) or key
    if override.text is not UNSET:
        text = override.text
    return key, text


def _overridden(value, default):
    return default if value is UNSET else value


def game_activity(session: Session, api: RobloxApi, *, show_account: bool, show_buttons: bool) -> dict:
    universe_id = session.universe_id or api.universe_for_place(session.place_id)
    game = api.game(universe_id) if universe_id else None

    if session.server_type is ServerType.PRIVATE:
        state = "In a private server"
    elif session.server_type is ServerType.RESERVED:
        state = "In a reserved server"
    elif game is not None:
        state = f"by {game.creator}" + (VERIFIED_BADGE if game.verified else "")
    else:
        state = None

    if game is not None:
        details = game.name
        large = (api.game_icon(universe_id) or ROBLOX_ICON, game.name)
    else:
        details = "In an experience"
        large = (ROBLOX_ICON, ROBLOX_NAME)

    small = (ROBLOX_ICON, ROBLOX_NAME)
    account = None
    if show_account and session.user_id is not None:
        user = api.user(session.user_id)
        headshot = api.headshot(session.user_id)
        if user is not None and headshot is not None:
            account = (headshot, f"Playing on {user.display_name} (@{user.name})")
            small = account

    overrides = session.overrides
    large = _image(overrides.large_image, *large, api)
    # The account picture is the player's own choice; a game does not replace it.
    if account is None:
        small = _image(overrides.small_image, *small, api)
    start = _overridden(overrides.start, session.joined_at)
    end = _overridden(overrides.end, None)

    buttons = []
    if show_buttons:
        if session.server_type is ServerType.PUBLIC:
            buttons.append(
                {
                    "label": "Join server",
                    "url": f"https://www.roblox.com/games/start?placeId={session.place_id}"
                    f"&gameInstanceId={session.job_id}",
                }
            )
        buttons.append({"label": "See game page", "url": f"https://www.roblox.com/games/{session.place_id}"})

    return _activity(
        details=_overridden(overrides.details, details),
        state=_overridden(overrides.state, state),
        start=_milliseconds(start),
        end=_milliseconds(end),
        large=large,
        small=small,
        buttons=buttons,
    )
