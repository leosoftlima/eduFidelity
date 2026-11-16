"""End-to-end invariants on the synthetic examples. Needs Chromium (Playwright)."""

from pathlib import Path

import pytest

from edufidelity.examples import run_examples
from edufidelity.models import MeasureRow
from edufidelity.pipeline import ReferenceAuthoringError, build_reference_from_html
from edufidelity.render import Renderer

pytestmark = pytest.mark.browser

PAGES = Path(__file__).resolve().parents[1] / "examples" / "pages"
PAGE_NAMES = ["lesson", "quiz", "overview"]


@pytest.fixture(scope="module")
def table(tmp_path_factory: pytest.TempPathFactory) -> dict[str, MeasureRow]:
    rows = run_examples(PAGES, tmp_path_factory.mktemp("build"))
    return {row.generated_id: row for row in rows}


def test_nothing_is_dropped(table: dict[str, MeasureRow]) -> None:
    assert len(table) == 12
    assert all(row.status == "ok" for row in table.values())


@pytest.mark.parametrize("page", PAGE_NAMES)
def test_faithful_copy_scores_maximum(table: dict[str, MeasureRow], page: str) -> None:
    row = table[f"{page}--faithful"]
    assert row.ep_f1 == 1.0
    assert row.layout_fidelity == pytest.approx(1.0, abs=1e-6)
    assert row.ssim == pytest.approx(1.0, abs=1e-6)
    assert (row.ped_essential, row.ped_supporting, row.ped_decorative) == (1.0, 1.0, 1.0)


@pytest.mark.parametrize("page", PAGE_NAMES)
def test_missing_essential_is_visible_in_its_category(
    table: dict[str, MeasureRow], page: str
) -> None:
    row = table[f"{page}--missing_essential"]
    assert row.ped_essential is not None and row.ped_essential < 1.0
    assert row.ped_decorative == 1.0
    assert row.ep_recall is not None and row.ep_recall < 1.0


@pytest.mark.parametrize("page", PAGE_NAMES)
def test_displacement_hits_layout_only(table: dict[str, MeasureRow], page: str) -> None:
    row = table[f"{page}--shifted"]
    assert row.ep_f1 == 1.0
    assert row.layout_fidelity is not None and row.layout_fidelity < 0.99
    assert (row.ped_essential, row.ped_supporting, row.ped_decorative) == (1.0, 1.0, 1.0)


@pytest.mark.parametrize("page", PAGE_NAMES)
def test_losing_decoration_spares_essentials(table: dict[str, MeasureRow], page: str) -> None:
    row = table[f"{page}--no_decorative"]
    assert row.ped_decorative == 0.0
    assert row.ped_essential == 1.0
    assert row.ssim is not None and row.ssim < 1.0


def test_unlabeled_reference_is_rejected(tmp_path: Path) -> None:
    page = tmp_path / "page.html"
    page.write_text("<!doctype html><body><p>No label here</p></body>", encoding="utf-8")
    with Renderer() as renderer, pytest.raises(ReferenceAuthoringError):
        build_reference_from_html(renderer, page, "x", 800, tmp_path / "ref.png")


def test_page_that_never_settles_is_a_recorded_failure(tmp_path: Path) -> None:
    page = tmp_path / "restless.html"
    # The height grows on every tick, so no two layout signatures can be equal. A random
    # height could repeat by chance between two polls and let the page "settle".
    page.write_text(
        "<!doctype html><body><div id='d'>x</div><script>"
        "let h = 0; setInterval(() => { h += 37;"
        " document.getElementById('d').style.height = h + 'px'; }, 20);</script></body>",
        encoding="utf-8",
    )
    with Renderer(timeout_ms=4000) as renderer:
        record, raw = renderer.render(page, 800, 600)
    assert record.status == "render_failure" and raw is None
    assert "stabilize" in record.reason


#: Tolerance across operating systems. The pages use bundled fonts, so text metrics
#: should agree; anti-aliasing may still differ by a few pixels. The CSV keeps 4 decimals.
_TOLERANCE = {
    "ssim": 0.02,
    "ep_f1": 1e-4,
    "layout_fidelity": 0.02,
    "ped_essential": 1e-4,
    "ped_supporting": 1e-4,
    "ped_decorative": 1e-4,
}


def test_table_matches_the_committed_one(table: dict[str, MeasureRow]) -> None:
    """examples/expected.csv was produced on Windows; CI checks it on Linux too."""
    import csv

    expected_path = PAGES.parent / "expected.csv"
    with expected_path.open(encoding="utf-8") as handle:
        expected = {row["generated_id"]: row for row in csv.DictReader(handle)}
    assert set(expected) == set(table)
    for generated_id, row in table.items():
        for name, tolerance in _TOLERANCE.items():
            value = getattr(row, name)
            assert value == pytest.approx(float(expected[generated_id][name]), abs=tolerance), (
                generated_id,
                name,
            )


def test_page_served_by_a_local_server_renders_by_url(tmp_path: Path) -> None:
    """Single-page applications need a server; only the allowed local origin opens."""
    import functools
    import http.server
    import threading

    (tmp_path / "index.html").write_text(
        "<!doctype html><body><h1 id='t'>waiting</h1>"
        "<img src='https://example.com/remote.png' alt='remote'>"
        "<script>const q = new URLSearchParams(location.search);"
        "document.getElementById('t').textContent = 'page ' + q.get('page');</script></body>",
        encoding="utf-8",
    )
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with Renderer(allowed_origins=(origin,)) as renderer:
            record, raw = renderer.render(f"{origin}/index.html?page=3", 800, 600)
    finally:
        server.shutdown()
    assert record.status == "ok" and raw is not None
    texts = [e.get("text") for e in raw["elements"]]
    assert "page 3" in texts


def test_only_local_origins_can_be_allowed() -> None:
    with pytest.raises(ValueError, match="local origins"):
        Renderer(allowed_origins=("https://example.com",))
