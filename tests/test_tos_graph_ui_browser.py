from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Iterator

import pytest


ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = ROOT / "config-templates" / "Services" / "tos-graph"
CONFIG_PATH = ROOT / "config-templates" / "Configs" / "tos-graph" / "config.yaml"
TOS_ROOT = Path(os.environ.get("AOA_TOS_ROOT", "/srv/AbyssOS/Tree-of-Sophia"))


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_TOS_GRAPH_UI_BROWSER_TEST") != "1",
    reason="set RUN_TOS_GRAPH_UI_BROWSER_TEST=1 for the tos-graph browser smoke",
)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_health(port: int) -> dict[str, object]:
    url = f"http://127.0.0.1:{port}/health"
    deadline = time.time() + 15
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # pragma: no cover - waiting loop
            last_error = exc
            time.sleep(0.25)
    raise AssertionError(f"tos-graph did not become healthy on {url}: {last_error}")


@pytest.fixture()
def tos_graph_server() -> Iterator[str]:
    if not TOS_ROOT.exists():
        pytest.skip(f"Tree-of-Sophia checkout is unavailable: {TOS_ROOT}")
    port = free_port()
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(SERVICE_ROOT),
            "TOS_GRAPH_TOS_ROOT": str(TOS_ROOT),
            "TOS_GRAPH_CONFIG_PATH": str(CONFIG_PATH),
        }
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        health = wait_for_health(port)
        assert health["philosophy_graph_projection_exists"] is True
        yield f"http://127.0.0.1:{port}"
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - cleanup path
            process.kill()


def test_tos_graph_philosophy_ui_renders_canvas_and_source_refs(tos_graph_server: str, tmp_path: Path) -> None:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - optional dependency route
        pytest.skip(f"playwright is not installed: {exc}")

    screenshot_path = os.environ.get("TOS_GRAPH_UI_SCREENSHOT_PATH")
    screenshot = Path(screenshot_path) if screenshot_path else tmp_path / "tos-graph-philosophy.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.goto(tos_graph_server, wait_until="networkidle")
            page.get_by_text("Tree of Sophia Graph").wait_for(timeout=10_000)
            page.locator("#inspector-title", has_text="Chronology Graph View").wait_for(timeout=10_000)
            page.get_by_role("button", name="Review packet").click()
            page.locator("#inspector-title", has_text="Review packet: chronology").wait_for(timeout=10_000)
            page.locator("#clusters-button").click()
            page.get_by_role("button", name="focused").click()
            page.locator("#graph canvas").first.wait_for(timeout=10_000)
            page.locator(".result-card").first.wait_for(timeout=10_000)
            page.locator(".predicate-toggle").first.wait_for(timeout=10_000)
            page.locator(".relation-card").first.wait_for(timeout=10_000)
            page.locator(".relation-card").first.click()
            page.locator(".detail-title", has_text="From").wait_for(timeout=10_000)
            page.locator(".detail-title", has_text="To").wait_for(timeout=10_000)
            first_result_title = page.locator(".result-card .result-title").first.inner_text(timeout=10_000)
            graph_caption = page.locator("#graph-caption").inner_text(timeout=10_000)
            relation_card_count = page.locator(".result-card .result-subtitle").filter(has_text="relations").count()
            predicate_toggle_count = page.locator(".predicate-toggle").count()
            node_count = page.locator("#graph canvas").count()
            source_ref_count = page.get_by_text("source_ref").count()
            page.screenshot(path=str(screenshot))
            browser.close()
    except PlaywrightError as exc:  # pragma: no cover - host browser route
        message = str(exc)
        if "Executable doesn't exist" in message or "Host system is missing dependencies" in message:
            pytest.skip(f"playwright browser is unavailable: {exc}")
        raise

    assert node_count > 0
    assert source_ref_count > 0
    assert "Corpus Or Prepared Source Document" not in first_result_title
    assert "links" in graph_caption
    assert relation_card_count > 0
    assert predicate_toggle_count > 0
    assert screenshot.stat().st_size > 20_000
