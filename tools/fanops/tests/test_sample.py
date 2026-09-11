import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from fanops import sample as S

ARTIST_HTML = (
    '<html><head><meta property="og:title" content="Laurin.">'
    '<meta property="og:description" content="Artist · {desc}"></head></html>'
)
CFG = {
    "artist": {"spotify_id": "1a9C2omo10kDc5F6UIW4gV"},
    "kit": {"repo": "Jul352mf/laurin-fan-kit"},
    "links": {"youtube_video_id": ""},
    "sampler": {"spotify_monthly_listeners": True, "github_stars": True},
}
NOW = datetime(2026, 9, 12, 6, 0, tzinfo=timezone.utc)


def artist_page(desc: str) -> str:
    return ARTIST_HTML.replace("{desc}", desc)


def make_client(routes):
    """routes: {url_prefix: handler(request) -> httpx.Response}"""
    def handler(request: httpx.Request) -> httpx.Response:
        for prefix, fn in routes.items():
            if str(request.url).startswith(prefix):
                return fn(request)
        return httpx.Response(404, text="no route")
    return httpx.Client(transport=httpx.MockTransport(handler))


# --- parsing: permit and deny -------------------------------------------------

@pytest.mark.parametrize("desc,expected", [
    ("0 monthly listeners.", 0),
    ("1,234 monthly listeners.", 1234),
    ("1.234.567 monthly listeners.", 1234567),
    ("12.5K monthly listeners.", 12500),
    ("2M monthly listeners.", 2_000_000),
])
def test_parse_monthly_listeners_permit(desc, expected):
    assert S.parse_monthly_listeners(artist_page(desc)) == expected


def test_parse_monthly_listeners_deny_absent():
    assert S.parse_monthly_listeners("<html><head><title>x</title></head></html>") is None
    assert S.parse_monthly_listeners(artist_page("Artist.")) is None


# --- collect --------------------------------------------------------------------

def test_collect_happy_path_and_youtube_skip_when_no_video_id():
    client = make_client({
        "https://open.spotify.com/artist/": lambda r: httpx.Response(200, text=artist_page("42 monthly listeners.")),
        "https://api.github.com/repos/": lambda r: httpx.Response(200, json={"stargazers_count": 7}),
    })
    res = S.collect(CFG, {}, client, NOW)
    assert res.failures == []
    assert [(s["source"], s["metric"], s["value"]) for s in res.samples] == [
        ("spotify", "monthly_listeners", 42), ("github", "stars", 7)]
    assert all(s["ts"] == "2026-09-12T06:00:00Z" for s in res.samples)
    assert res.skipped == ["youtube: no video id configured"]


def test_collect_youtube_enabled_without_key_is_a_loud_failure():
    cfg = json.loads(json.dumps(CFG))
    cfg["links"]["youtube_video_id"] = "abc123"
    client = make_client({
        "https://open.spotify.com/artist/": lambda r: httpx.Response(200, text=artist_page("1 monthly listeners.")),
        "https://api.github.com/repos/": lambda r: httpx.Response(200, json={"stargazers_count": 0}),
    })
    res = S.collect(cfg, {}, client, NOW)
    assert any("YOUTUBE_API_KEY missing" in f for f in res.failures)
    assert len(res.samples) == 2  # the other sources still land


def test_collect_youtube_with_key():
    cfg = json.loads(json.dumps(CFG))
    cfg["links"]["youtube_video_id"] = "abc123"
    seen = {}

    def yt(r):
        seen["key"] = r.url.params.get("key")
        seen["id"] = r.url.params.get("id")
        return httpx.Response(200, json={"items": [{"statistics": {"viewCount": "150", "likeCount": "9", "commentCount": "2"}}]})

    client = make_client({
        "https://open.spotify.com/artist/": lambda r: httpx.Response(200, text=artist_page("1 monthly listeners.")),
        "https://api.github.com/repos/": lambda r: httpx.Response(200, json={"stargazers_count": 0}),
        "https://www.googleapis.com/youtube/v3/videos": yt,
    })
    res = S.collect(cfg, {"YOUTUBE_API_KEY": "k"}, client, NOW)
    assert res.failures == []
    assert seen == {"key": "k", "id": "abc123"}
    yt_metrics = {s["metric"]: s["value"] for s in res.samples if s["source"] == "youtube"}
    assert yt_metrics == {"views": 150, "likes": 9, "comments": 2}


def test_collect_github_error_is_reported_and_others_still_written():
    client = make_client({
        "https://open.spotify.com/artist/": lambda r: httpx.Response(200, text=artist_page("3 monthly listeners.")),
        "https://api.github.com/repos/": lambda r: httpx.Response(503, text="down"),
    })
    res = S.collect(CFG, {}, client, NOW)
    assert len(res.failures) == 1 and res.failures[0].startswith("github.stars:")
    assert [s["metric"] for s in res.samples] == ["monthly_listeners"]


def test_collect_spotify_page_without_listeners_fails_not_zero():
    """A page that lost the meta tag must not be recorded as 0 listeners."""
    client = make_client({
        "https://open.spotify.com/artist/": lambda r: httpx.Response(200, text="<html></html>"),
        "https://api.github.com/repos/": lambda r: httpx.Response(200, json={"stargazers_count": 0}),
    })
    res = S.collect(CFG, {}, client, NOW)
    assert any(f.startswith("spotify.monthly_listeners:") for f in res.failures)
    assert not any(s["source"] == "spotify" for s in res.samples)


# --- storage --------------------------------------------------------------------

def test_append_jsonl_round_trip(tmp_path: Path):
    out = tmp_path / "data" / "samples.jsonl"
    n = S.append_jsonl(out, [{"ts": "2026-09-12T06:00:00Z", "source": "github", "metric": "stars", "value": 7}])
    assert n == 1
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines == ['{"ts":"2026-09-12T06:00:00Z","source":"github","metric":"stars","value":7}']
    S.append_jsonl(out, [{"ts": "t2", "source": "github", "metric": "stars", "value": 8}])
    assert len(out.read_text(encoding="utf-8").splitlines()) == 2


def test_main_exit_code_reflects_failures_and_dry_run_writes_nothing(tmp_path: Path, monkeypatch):
    root = tmp_path
    (root / "data").mkdir()
    (root / "config.json").write_text(json.dumps(CFG), encoding="utf-8")

    def fake_collect(cfg, env, client, now):
        r = S.Result()
        r.failures.append("github.stars: boom")
        r.add("t", "spotify", "monthly_listeners", 5)
        return r

    monkeypatch.setattr(S, "collect", fake_collect)
    assert S.main(["--root", str(root)]) == 1
    assert (root / "data" / "samples.jsonl").read_text(encoding="utf-8").count("\n") == 1
    assert S.main(["--root", str(root), "--dry-run"]) == 1
    assert (root / "data" / "samples.jsonl").read_text(encoding="utf-8").count("\n") == 1
