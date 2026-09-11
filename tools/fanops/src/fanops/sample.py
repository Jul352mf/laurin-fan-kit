"""Collect public numbers for the fan kit and append them to data/samples.jsonl.

Sources (all public, no Spotify developer app involved):
  spotify.monthly_listeners     from the artist page's og:description meta tag
  github.stars                  from the public GitHub API
  youtube.views/likes/comments  via YouTube Data API v3 (only when a video id is configured)

Every enabled source that fails makes the run exit non-zero, after the successes are written.
Values are printed beside the verdict so a log line can be audited at a glance.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

UA = "laurin-fan-kit sampler (+https://github.com/Jul352mf/laurin-fan-kit)"
_LISTENERS_RE = re.compile(r"(\d[\d.,\s]*)\s*([KkMm])?\s*monthly listeners", re.IGNORECASE)
_OG_DESC_RE = re.compile(r'<meta\s+property="og:description"\s+content="([^"]*)"', re.IGNORECASE)


def repo_root() -> Path:
    """tools/fanops/src/fanops/sample.py -> repository root, unless FANOPS_ROOT overrides it."""
    env = os.environ.get("FANOPS_ROOT")
    return Path(env).resolve() if env else Path(__file__).resolve().parents[4]


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def parse_monthly_listeners(html: str) -> int | None:
    """Return the monthly-listener count from a Spotify artist page, or None when absent."""
    m = _OG_DESC_RE.search(html)
    haystack = m.group(1) if m else html
    m2 = _LISTENERS_RE.search(haystack)
    if not m2:
        return None
    raw = re.sub(r"\s", "", m2.group(1))
    suffix = (m2.group(2) or "").upper()
    if suffix:
        num = float(raw.replace(",", "."))
        return int(round(num * (1_000 if suffix == "K" else 1_000_000)))
    return int(re.sub(r"[.,]", "", raw))


@dataclass
class Result:
    samples: list[dict] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def add(self, ts: str, source: str, metric: str, value: int) -> None:
        self.samples.append({"ts": ts, "source": source, "metric": metric, "value": value})


def fetch_spotify_monthly_listeners(client: httpx.Client, artist_id: str) -> int:
    r = client.get(
        f"https://open.spotify.com/artist/{artist_id}",
        headers={"User-Agent": UA, "Accept-Language": "en"},
        follow_redirects=True,
        timeout=20,
    )
    r.raise_for_status()
    n = parse_monthly_listeners(r.text)
    if n is None:
        raise ValueError("no 'monthly listeners' in og:description")
    return n


def fetch_github_stars(client: httpx.Client, repo: str, token: str | None) -> int:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": UA}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = client.get(f"https://api.github.com/repos/{repo}", headers=headers, timeout=20)
    r.raise_for_status()
    n = r.json().get("stargazers_count")
    if not isinstance(n, int):
        raise ValueError("stargazers_count missing")
    return n


def fetch_youtube_stats(client: httpx.Client, video_id: str, api_key: str) -> dict[str, int]:
    r = client.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={"part": "statistics", "id": video_id, "key": api_key},
        headers={"User-Agent": UA},
        timeout=20,
    )
    r.raise_for_status()
    items = r.json().get("items") or []
    if not items:
        raise ValueError(f"video {video_id} not found")
    st = items[0].get("statistics", {})
    out: dict[str, int] = {}
    for key, name in (("viewCount", "views"), ("likeCount", "likes"), ("commentCount", "comments")):
        if key in st:
            out[name] = int(st[key])
    if "views" not in out:
        raise ValueError("viewCount missing")
    return out


def collect(cfg: dict, env: dict, client: httpx.Client, now: datetime) -> Result:
    ts = now.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    res = Result()
    sampler = cfg.get("sampler", {})

    if sampler.get("spotify_monthly_listeners", True):
        try:
            res.add(ts, "spotify", "monthly_listeners", fetch_spotify_monthly_listeners(client, cfg["artist"]["spotify_id"]))
        except Exception as exc:  # noqa: BLE001 - every failure is reported, none swallowed
            res.failures.append(f"spotify.monthly_listeners: {exc}")

    if sampler.get("github_stars", True):
        try:
            res.add(ts, "github", "stars", fetch_github_stars(client, cfg["kit"]["repo"], env.get("GITHUB_TOKEN")))
        except Exception as exc:  # noqa: BLE001
            res.failures.append(f"github.stars: {exc}")

    video_id = (cfg.get("links", {}).get("youtube_video_id") or "").strip()
    if not video_id:
        res.skipped.append("youtube: no video id configured")
    else:
        key = env.get("YOUTUBE_API_KEY")
        if not key:
            res.failures.append("youtube: YOUTUBE_API_KEY missing while a video id is configured")
        else:
            try:
                for metric, value in fetch_youtube_stats(client, video_id, key).items():
                    res.add(ts, "youtube", metric, value)
            except Exception as exc:  # noqa: BLE001
                res.failures.append(f"youtube: {exc}")
    return res


def append_jsonl(path: Path, samples: list[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for s in samples:
            fh.write(json.dumps(s, ensure_ascii=False, separators=(",", ":")) + "\n")
    return len(samples)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--root", type=Path, default=None, help="repository root (default: derived from this file, or FANOPS_ROOT)")
    ap.add_argument("--dry-run", action="store_true", help="print values, write nothing")
    args = ap.parse_args(argv)
    root = args.root.resolve() if args.root else repo_root()
    cfg = load_config(root / "config.json")
    out = root / cfg.get("sampler", {}).get("jsonl_path", "data/samples.jsonl")

    with httpx.Client() as client:
        res = collect(cfg, dict(os.environ), client, datetime.now(timezone.utc))

    for s in res.samples:
        print(f"OK    {s['source']}.{s['metric']} = {s['value']}  ({s['ts']})")
    for s in res.skipped:
        print(f"SKIP  {s}")
    for f in res.failures:
        print(f"FAIL  {f}")

    if args.dry_run:
        print(f"DRY   would append {len(res.samples)} line(s) to {out}")
    else:
        n = append_jsonl(out, res.samples)
        print(f"WROTE {n} line(s) -> {out}")
    return 1 if res.failures else 0


if __name__ == "__main__":
    sys.exit(main())
