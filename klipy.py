from __future__ import annotations

import random
from typing import Any

import aiohttp

from config import KLIPY_API_KEY


class KlipyError(Exception):
    pass


async def fetch_random_klipy_gif(query: str) -> dict[str, Any]:
    """Search Klipy and return a random GIF: {url, title, id}."""
    if not KLIPY_API_KEY:
        raise KlipyError("missing KLIPY_API_KEY")
    q = (query or "").strip()
    if not q:
        raise KlipyError("query is required")

    url = f"https://api.klipy.com/api/v1/{KLIPY_API_KEY}/gifs/search"
    params = {"q": q, "per_page": "20"}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status != 200:
                text = response.reason or ""
                raise KlipyError(f"Klipy {response.status} {text}".strip())
            body = await response.json()

    items = (body or {}).get("data", {}).get("data")
    if not isinstance(items, list) or not items:
        raise KlipyError("no GIF found")

    item = random.choice(items)
    file_info = item.get("file") or {}
    gif_url = (
        ((file_info.get("md") or {}).get("gif") or {}).get("url")
        or ((file_info.get("hd") or {}).get("gif") or {}).get("url")
        or ((file_info.get("sm") or {}).get("gif") or {}).get("url")
    )
    if not gif_url:
        raise KlipyError("no GIF URL in response")

    return {
        "url": gif_url,
        "title": item.get("title") or q,
        "id": item.get("id"),
    }
