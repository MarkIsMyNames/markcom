import logging
from asyncio import AbstractEventLoop
from collections.abc import Awaitable, Callable

from nicegui import Event, core
from nicegui.functions.refreshable import refreshable

logger: logging.Logger = logging.getLogger(__name__)


def announce(changed: Event[[]]) -> None:
    loop: AbstractEventLoop | None = core.loop
    if loop is None:
        logger.debug("change announced before NiceGUI started, so nothing to redraw")
        return
    logger.debug("change announced")
    # emit schedules on its calling loop, so run it on NiceGUI's; stopped or closed loop: quitting
    try:
        loop.call_soon_threadsafe(changed.emit)
    except RuntimeError:
        logger.debug("change announced as NiceGUI closed, so ignored")


def keep_current[State](
    read: Callable[[], State], body: refreshable[[State], None], changed: Event[[]]
) -> Callable[[], Awaitable[None]]:
    shown: State = read()
    body(shown)
    logger.debug("page drawn")

    async def redraw_if_changed() -> None:
        nonlocal shown
        now: State = read()
        # redraw would close the page's open dialogs
        if now == shown:
            logger.debug("state unchanged, so no redraw")
            return
        shown = now
        logger.debug("state changed, so redrawing")
        await body.refresh(now)

    # subscribed from the page, so ends with its client
    changed.subscribe(redraw_if_changed)
    return redraw_if_changed
