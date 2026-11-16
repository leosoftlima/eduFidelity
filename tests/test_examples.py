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
    page.write_text(
        "<!doctype html><body><div id='d'>x</div><script>"
        "setInterval(() => { const d = document.getElementById('d');"
        " d.style.height = (Math.random() * 500) + 'px'; }, 20);</script></body>",
        encoding="utf-8",
    )
    with Renderer(timeout_ms=1500) as renderer:
        record, raw = renderer.render(page, 800, 600)
    assert record.status == "render_failure" and raw is None
    assert "stabilize" in record.reason
