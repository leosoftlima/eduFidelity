"""Controlled rendering: one fixed environment for every page.

* Chromium pinned by the installed Playwright version; device scale factor 1.
* Viewport equal to the reference frame.
* Animations and transitions disabled; reduced motion requested.
* Network closed: only ``file:`` and ``data:`` resources load, so a render cannot
  depend on a remote asset that changes or disappears. A page served by a local server
  (a single-page application, for example) can be rendered by URL; only the origins
  listed in ``allowed_origins`` are then opened, and nothing else.
* A page is captured only after load, fonts ready, images decoded and two
  consecutive identical layout signatures. A page that never settles is a
  ``render_failure`` with a reason; it is never silently dropped.
"""

from __future__ import annotations

import time
from pathlib import Path
from types import TracebackType
from typing import Any

from playwright.sync_api import Browser, Error, Playwright, Route, sync_playwright

from .collector import COLLECTOR_JS, FREEZE_CSS, LAYOUT_SIGNATURE_JS
from .models import BBox, DomSnapshot, Element, ElementType, RenderRecord

_READY_JS = """
async () => {
  await document.fonts.ready;
  await Promise.all(Array.from(document.images).map(
    (img) => img.decode ? img.decode().catch(() => undefined) : undefined));
}
"""


class Renderer:
    """Reuses one browser across pages. Use as a context manager."""

    def __init__(
        self,
        timeout_ms: int = 15_000,
        poll_ms: int = 100,
        allowed_origins: tuple[str, ...] = (),
    ) -> None:
        self.timeout_ms = timeout_ms
        self.poll_ms = poll_ms
        for origin in allowed_origins:
            if not origin.startswith(("http://127.0.0.1:", "http://localhost:")):
                raise ValueError(f"only local origins can be allowed: {origin!r}")
        self.allowed_origins = tuple(o.rstrip("/") + "/" for o in allowed_origins)
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    def __enter__(self) -> Renderer:
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

    def render(
        self,
        html: Path | str,
        frame_width: int,
        frame_height: int,
        screenshot: Path | None = None,
        *,
        reference_mode: bool = False,
    ) -> tuple[RenderRecord, dict[str, Any] | None]:
        """Render ``html`` and return the record plus the raw collector output."""
        assert self._browser is not None, "use Renderer as a context manager"
        viewport_height = min(frame_height, 4000)
        record = RenderRecord(
            status="render_failure",
            browser=f"chromium {self._browser.version}",
            viewport_width=frame_width,
            viewport_height=viewport_height,
        )
        context = self._browser.new_context(
            viewport={"width": frame_width, "height": viewport_height},
            device_scale_factor=1,
            reduced_motion="reduce",
        )
        context.route("**/*", self._route)
        page = context.new_page()
        started = time.monotonic()
        try:
            target = html if isinstance(html, str) else html.resolve().as_uri()
            if isinstance(html, str) and not html.startswith(self.allowed_origins or ("file:",)):
                raise ValueError(f"{html!r} is not under an allowed origin")
            page.goto(target, wait_until="load", timeout=self.timeout_ms)
            page.add_style_tag(content=FREEZE_CSS)
            page.evaluate(_READY_JS)
            if not self._wait_stable(page, started):
                record.reason = "layout did not stabilize before the timeout"
                return record, None
            raw: dict[str, Any] = page.evaluate(
                COLLECTOR_JS,
                {
                    "frameWidth": frame_width,
                    "frameHeight": frame_height,
                    "referenceMode": reference_mode,
                },
            )
            if screenshot is not None:
                screenshot.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(screenshot), full_page=True, animations="disabled")
                record.screenshot = str(screenshot)
            record.status = "ok"
            record.stable_after_ms = int((time.monotonic() - started) * 1000)
            return record, raw
        except Error as error:
            record.reason = str(error).splitlines()[0]
            return record, None
        finally:
            context.close()

    def _wait_stable(self, page: Any, started: float) -> bool:
        previous: str | None = None
        while (time.monotonic() - started) * 1000 < self.timeout_ms:
            signature: str = page.evaluate(LAYOUT_SIGNATURE_JS)
            if signature == previous:
                return True
            previous = signature
            page.wait_for_timeout(self.poll_ms)
        return False

    def _route(self, route: Route) -> None:
        url = route.request.url
        if url.startswith(("file:", "data:", "about:", "blob:", *self.allowed_origins)):
            route.continue_()
        else:
            route.abort()


def to_snapshot(raw: dict[str, Any], frame_width: int, frame_height: int) -> DomSnapshot:
    """Convert collector output into a snapshot with ids in document order."""
    elements = [
        Element(
            id=f"g{index:04d}",
            type=ElementType(item["type"]),
            text=item.get("text") or "",
            bbox=BBox(x=item["x"], y=item["y"], w=item["w"], h=item["h"]),
            asset=item.get("asset"),
        )
        for index, item in enumerate(raw["elements"], start=1)
    ]
    return DomSnapshot(
        frame_width=frame_width,
        frame_height=frame_height,
        page_height=int(raw["pageHeight"]),
        elements=elements,
    )
