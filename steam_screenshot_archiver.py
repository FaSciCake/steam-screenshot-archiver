#!/usr/bin/env python3
"""Download and archive screenshots exposed by Steam's Published File API."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

API_URL = "https://api.steampowered.com/IPublishedFileService/GetUserFiles/v1/"
RESOLVE_URL = "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/"
TIMEOUT = (15, 90)
USER_AGENT = "SteamScreenshotArchiver/1.0"
IMAGE_HOSTS = ("steamusercontent.com", "steamstatic.com", "akamaihd.net")


def log(message: str = "") -> None:
    print(message, flush=True)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_manifest(path: Path, data: dict[str, Any]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)


def resolve_steam_id(value: str, key: str, session: requests.Session) -> str:
    value = value.strip().rstrip("/")
    if value.startswith(("https://", "http://")):
        parsed = urlparse(value)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] in ("profiles", "id"):
            value = parts[1]
        else:
            raise ValueError("Use a Steam profile URL in /profiles/ID or /id/name format.")
    if value.isdigit():
        if len(value) != 17:
            raise ValueError("A numeric SteamID64 must contain 17 digits.")
        return value

    response = session.get(
        RESOLVE_URL, params={"key": key, "vanityurl": value}, timeout=TIMEOUT
    )
    response.raise_for_status()
    result = response.json().get("response", {})
    if result.get("success") != 1 or not result.get("steamid"):
        raise ValueError(f"Steam could not resolve vanity name {value!r}.")
    return str(result["steamid"])


def fetch_screenshots(
    session: requests.Session, key: str, steam_id: str, page_size: int
) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    page = 1
    reported_total = None
    while True:
        log(f"Reading Steam API page {page}...")
        response = session.get(
            API_URL,
            params={
                "key": key,
                "steamid": steam_id,
                "filetype": 4,
                "numperpage": page_size,
                "page": page,
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        api_result = response.json().get("response")
        if not isinstance(api_result, dict):
            raise RuntimeError("Steam returned an unexpected API response.")
        try:
            reported_total = int(api_result.get("total"))
        except (TypeError, ValueError):
            pass
        details = api_result.get("publishedfiledetails") or []
        if not isinstance(details, list) or not details:
            break

        added = 0
        for item in details:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("publishedfileid", "")).strip()
            if item_id and item_id not in found:
                found[item_id] = item
                added += 1

        log(f"  {len(found)} unique screenshots" +
            (f" / {reported_total} reported" if reported_total is not None else ""))
        if added == 0 or (reported_total is not None and len(found) >= reported_total):
            break
        if len(details) < page_size:
            break
        page += 1

    return sorted(
        found.values(),
        key=lambda item: (
            int(item.get("time_created") or 0),
            str(item.get("consumer_appid") or 0),
            str(item.get("publishedfileid") or ""),
        ),
    )


def timestamp_for(item: dict[str, Any]) -> tuple[int, str]:
    try:
        stamp = int(item.get("time_created"))
        if stamp <= 0:
            raise ValueError
        return stamp, datetime.fromtimestamp(stamp, timezone.utc).strftime("%Y%m%d%H%M%S")
    except (TypeError, ValueError, OverflowError, OSError):
        return 0, f"unknown_{item.get('publishedfileid', 'unknown')}"


def image_extension(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    raise ValueError("The response was not a recognised JPG, PNG, or WEBP image.")


def download_one(
    item: dict[str, Any], destination: Path, headers: dict[str, str]
) -> dict[str, Any]:
    url = str(item.get("file_url") or "").strip()
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not any(
        host == suffix or host.endswith("." + suffix) for suffix in IMAGE_HOSTS
    ):
        raise ValueError("Steam supplied an unexpected or unsupported image URL.")

    temp = destination.with_name(
        destination.name + f".{item.get('publishedfileid', 'unknown')}.part"
    )
    last_error: Exception | None = None
    for attempt in range(1, 5):
        try:
            with requests.get(url, headers=headers, timeout=TIMEOUT, stream=True) as response:
                response.raise_for_status()
                size = 0
                first = bytearray()
                with temp.open("wb") as output:
                    for chunk in response.iter_content(256 * 1024):
                        if not chunk:
                            continue
                        if len(first) < 16:
                            first.extend(chunk[: 16 - len(first)])
                        output.write(chunk)
                        size += len(chunk)
                if size == 0:
                    raise ValueError("Steam returned an empty image.")
                extension = image_extension(bytes(first))
                final_path = destination.with_suffix(extension)
                os.replace(temp, final_path)
                return {"path": final_path, "size": size}
        except Exception as exc:
            last_error = exc
            temp.unlink(missing_ok=True)
            if attempt < 4:
                time.sleep(min(2 ** attempt, 12))
    raise RuntimeError(f"Download failed after four attempts: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Archive Steam screenshots into AppID folders with a JSON manifest."
    )
    parser.add_argument("--steamid", help="SteamID64, vanity name, or Steam profile URL.")
    parser.add_argument("--output", default="SteamScreenshotArchive", help="Archive folder.")
    parser.add_argument("--workers", type=int, default=4, help="Parallel downloads (1-8).")
    parser.add_argument("--per-page", type=int, default=100, help="API page size (1-100).")
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        parser.error("--workers must be between 1 and 8.")
    if not 1 <= args.per_page <= 100:
        parser.error("--per-page must be between 1 and 100.")

    key = getpass.getpass("Steam Web API key (input is hidden): ").strip()
    if not key:
        log("No API key supplied.")
        return 2

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    try:
        identity = args.steamid or input("SteamID64, vanity name, or profile URL: ").strip()
        steam_id = resolve_steam_id(identity, key, session)
        log(f"Resolved Steam account: {steam_id}")

        root = Path(args.output).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        manifest_path = root / "manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                backup = root / f"manifest.corrupt-{int(time.time())}.json"
                manifest_path.replace(backup)
                log(f"Unreadable manifest moved to {backup.name}.")
                manifest = {}
        else:
            manifest = {}

        manifest.setdefault("schema_version", 1)
        manifest["steamid"] = steam_id
        manifest["updated_at_utc"] = utc_now()
        manifest["timestamp_note"] = (
            "UTC timestamps come from Steam API time_created, the published-file "
            "timestamp; it is not guaranteed to be the original capture time."
        )
        manifest.setdefault("screenshots", {})

        items = fetch_screenshots(session, key, steam_id, args.per_page)
        if not items:
            log("Steam returned no screenshots. Check the account and screenshot visibility.")
            save_manifest(manifest_path, manifest)
            return 0
        log(f"\nFound {len(items)} unique screenshots.")

        # Stable suffixes prevent collisions for screenshots sharing an AppID and second.
        counters: dict[tuple[str, str], int] = {}
        jobs = []
        for item in items:
            item_id = str(item["publishedfileid"])
            app_id = str(item.get("consumer_appid") or "unknown_app")
            stamp, stamp_text = timestamp_for(item)
            key_tuple = (app_id, stamp_text)
            counters[key_tuple] = counters.get(key_tuple, 0) + 1
            folder = root / app_id
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / f"{stamp_text}_{counters[key_tuple]}.jpg"
            record = manifest["screenshots"].get(item_id, {})
            previous = root / record["relative_path"] if record.get("relative_path") else None
            if previous and previous.is_file() and previous.stat().st_size:
                record.update({
                    "status": "downloaded",
                    "last_seen_at_utc": utc_now(),
                    "time_created_unix": stamp or item.get("time_created"),
                    "relative_path": previous.relative_to(root).as_posix(),
                })
                manifest["screenshots"][item_id] = record
            else:
                jobs.append((item, target, stamp))

        save_manifest(manifest_path, manifest)
        log(f"Already archived: {len(items) - len(jobs)}; to download: {len(jobs)}.")
        completed = failed = 0
        headers = {"User-Agent": USER_AGENT}
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(download_one, item, target, headers): (item, target, stamp)
                for item, target, stamp in jobs
            }
            for future in as_completed(futures):
                item, target, stamp = futures[future]
                item_id = str(item["publishedfileid"])
                try:
                    result = future.result()
                    path = result["path"]
                    if stamp:
                        os.utime(path, (stamp, stamp))
                    manifest["screenshots"][item_id] = {
                        "publishedfileid": item_id,
                        "consumer_appid": item.get("consumer_appid"),
                        "title": item.get("title"),
                        "time_created_unix": stamp or item.get("time_created"),
                        "time_created_utc": datetime.fromtimestamp(stamp, timezone.utc).isoformat() if stamp else None,
                        "time_updated_unix": item.get("time_updated"),
                        "file_url": item.get("file_url"),
                        "preview_url": item.get("preview_url"),
                        "file_size_api": item.get("file_size"),
                        "downloaded_size": result["size"],
                        "relative_path": path.relative_to(root).as_posix(),
                        "status": "downloaded",
                        "downloaded_at_utc": utc_now(),
                    }
                    completed += 1
                    log(f"[{completed + failed}/{len(jobs)}] Downloaded {path}")
                except Exception as exc:
                    manifest["screenshots"][item_id] = {
                        "publishedfileid": item_id,
                        "consumer_appid": item.get("consumer_appid"),
                        "title": item.get("title"),
                        "time_created_unix": stamp or item.get("time_created"),
                        "file_url": item.get("file_url"),
                        "status": "failed",
                        "error": str(exc),
                        "last_attempt_at_utc": utc_now(),
                    }
                    failed += 1
                    log(f"[{completed + failed}/{len(jobs)}] FAILED {item_id}: {exc}")
                manifest["updated_at_utc"] = utc_now()
                save_manifest(manifest_path, manifest)

        log(f"\nFinished. Downloaded: {completed}; already archived: {len(items) - len(jobs)}; failed: {failed}.")
        log(f"Manifest: {manifest_path}")
        return 1 if failed else 0
    except requests.HTTPError as exc:
        log(f"HTTP error: {exc}")
        if exc.response is not None:
            log(f"Steam response: {exc.response.text[:1000]}")
        return 1
    except (requests.RequestException, ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        log(f"Error: {exc}")
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
