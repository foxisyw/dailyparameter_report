"""Vercel Blob upload client — stdlib only (no httpx)."""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BLOB_API = "https://blob.vercel-storage.com"
TIMEOUT = 30


def _get_token() -> str:
    token = os.environ.get("BLOB_READ_WRITE_TOKEN", "")
    if not token:
        raise RuntimeError(
            "BLOB_READ_WRITE_TOKEN environment variable is not set. "
            "Set it to your Vercel Blob read-write token."
        )
    return token


def upload(path: str, content: bytes | str, content_type: str = "application/octet-stream") -> str:
    """Upload a file to Vercel Blob.

    Parameters
    ----------
    path : str
        The pathname for the blob (e.g. ``reports/2026-03-26/report.json``).
    content : bytes | str
        File content.  Strings are encoded to UTF-8.
    content_type : str
        MIME type for the blob.

    Returns
    -------
    str
        The public URL of the uploaded blob.
    """
    token = _get_token()

    if isinstance(content, str):
        body = content.encode("utf-8")
    else:
        body = content

    url = BLOB_API
    headers = {
        "Authorization": f"Bearer {token}",
        "x-api-version": "7",
        "content-type": content_type,
        "x-pathname": path,
    }

    req = Request(url, data=body, headers=headers, method="PUT")
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            result = json.loads(resp.read())
        return result.get("url", "")
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Vercel Blob upload failed ({exc.code}): {error_body}"
        ) from exc


def list_blobs(prefix: str = "") -> list[dict]:
    """List blobs under a given prefix.

    Parameters
    ----------
    prefix : str
        Filter blobs whose pathname starts with this prefix.

    Returns
    -------
    list[dict]
        Each dict has at least ``url`` and ``pathname`` keys.
    """
    token = _get_token()

    url = f"{BLOB_API}?prefix={prefix}"
    headers = {
        "Authorization": f"Bearer {token}",
        "x-api-version": "7",
    }

    req = Request(url, headers=headers, method="GET")
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            result = json.loads(resp.read())
        return result.get("blobs", [])
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Vercel Blob list failed ({exc.code}): {error_body}"
        ) from exc
