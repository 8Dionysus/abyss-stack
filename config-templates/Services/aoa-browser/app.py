from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from urllib.parse import urlparse
import base64
import ipaddress

from playwright.async_api import async_playwright


app = FastAPI()


def is_private_host(host: str) -> bool:
    if host in ("localhost", "127.0.0.1", "::1"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return False


def validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(400, "Only http/https allowed")
    if not parsed.hostname:
        raise HTTPException(400, "Bad URL")
    if is_private_host(parsed.hostname):
        raise HTTPException(403, "Local/private hosts blocked")


class ReadReq(BaseModel):
    url: str
    wait_ms: int = 800
    max_chars: int = 80000


class ShotReq(BaseModel):
    url: str
    full_page: bool = True


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/read")
async def read(req: ReadReq) -> dict[str, str]:
    validate_url(req.url)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(req.url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(req.wait_ms)
        title = await page.title()
        text = await page.inner_text("body")
        await browser.close()
    if len(text) > req.max_chars:
        text = text[: req.max_chars] + "\n...[TRUNCATED]"
    return {"url": req.url, "title": title, "text": text}


@app.post("/screenshot")
async def screenshot(req: ShotReq) -> dict[str, str]:
    validate_url(req.url)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 720})
        await page.goto(req.url, wait_until="domcontentloaded", timeout=45000)
        png = await page.screenshot(full_page=req.full_page)
        await browser.close()
    return {"url": req.url, "pngBase64": base64.b64encode(png).decode("ascii")}
