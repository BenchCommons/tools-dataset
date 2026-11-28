"""Spec 004, R2: download cache, tested against a local HTTP server.

Ported from BenchCommons/dataset-names@e7e8405 tests/test_cache.py (spec 002 R4, spec 003 R4,
spec 003e R4.1 of dataset-names). Test vectors unchanged; messages in English.
"""

import hashlib
import json
from datetime import datetime

import pytest

import datasettool
from datasettool.sources.adapters import Resource
from datasettool.sources.cache import (
    DEFAULT_USER_AGENT, BlockedError, FetchError, cached_path, fetch_resource, make_user_agent,
)

BODY = "nome,sexo,ano,quantidade\nMARIA,F,2020,100\n".encode()


def _resource(server, path="/a.csv", body=BODY):
    server.files[path] = body
    return Resource(server.url(path), path.lstrip("/"))


def test_downloads_and_writes_metadata(server, tmp_path):
    dest = fetch_resource(tmp_path, "exemplo", _resource(server))
    assert dest == tmp_path / "exemplo" / "a.csv" == cached_path(tmp_path, "exemplo", "a.csv")
    assert dest.read_bytes() == BODY
    meta = json.loads((tmp_path / "exemplo" / "a.csv.meta.json").read_text(encoding="utf-8"))
    assert set(meta) == {"url", "downloaded_at", "sha256", "size"}
    assert meta["url"] == server.url("/a.csv")
    assert meta["sha256"] == hashlib.sha256(BODY).hexdigest()
    assert meta["size"] == len(BODY)
    assert datetime.fromisoformat(meta["downloaded_at"]).tzinfo is not None


def test_default_user_agent_identifies_dataset_tool(server, tmp_path):
    fetch_resource(tmp_path, "exemplo", _resource(server))
    agent = server.requests[0][1]
    assert agent == DEFAULT_USER_AGENT
    assert agent == f"tools-dataset/{datasettool.__version__} (+https://github.com/BenchCommons/tools-dataset)"


def test_user_agent_identifies_the_dataset_and_its_repository(server, tmp_path):
    # dataset-names' header, byte for byte: namescommons/<version> (+<repo>).
    agent = make_user_agent("namescommons", "0.1.0", "https://github.com/BenchCommons/dataset-names")
    fetch_resource(tmp_path, "exemplo", _resource(server), user_agent=agent)
    sent = server.requests[0][1]
    assert sent == "namescommons/0.1.0 (+https://github.com/BenchCommons/dataset-names)"
    assert sent.startswith("namescommons/")
    assert "https://github.com/BenchCommons/dataset-names" in sent


def test_cached_file_is_not_downloaded_again(server, tmp_path):
    r = _resource(server)
    fetch_resource(tmp_path, "exemplo", r)
    fetch_resource(tmp_path, "exemplo", r)
    assert server.paths() == ["/a.csv"]


def test_refresh_downloads_again(server, tmp_path):
    r = _resource(server)
    fetch_resource(tmp_path, "exemplo", r)
    server.files["/a.csv"] = b"novo\n"
    dest = fetch_resource(tmp_path, "exemplo", r, refresh=True)
    assert server.paths() == ["/a.csv", "/a.csv"]
    assert dest.read_bytes() == b"novo\n"
    meta = json.loads((tmp_path / "exemplo" / "a.csv.meta.json").read_text(encoding="utf-8"))
    assert meta["size"] == 5


def test_offline_uses_the_cache_without_network(server, tmp_path):
    r = _resource(server)
    fetch_resource(tmp_path, "exemplo", r)
    assert fetch_resource(tmp_path, "exemplo", r, offline=True).read_bytes() == BODY
    assert server.paths() == ["/a.csv"]


def test_offline_without_cache_fails_without_network(server, tmp_path):
    with pytest.raises(FetchError, match="a.csv missing from the cache and --offline"):
        fetch_resource(tmp_path, "exemplo", _resource(server), offline=True)
    assert server.requests == []


def test_offline_and_refresh_together_are_refused(server, tmp_path):
    with pytest.raises(ValueError, match="incompatible"):
        fetch_resource(tmp_path, "exemplo", _resource(server), offline=True, refresh=True)


def test_interrupted_download_does_not_stay_in_the_cache(server, tmp_path):
    r = _resource(server)
    server.truncated.add("/a.csv")
    with pytest.raises(FetchError, match="incomplete"):
        fetch_resource(tmp_path, "exemplo", r, backoff=0)
    assert list((tmp_path / "exemplo").iterdir()) == []


def test_interrupted_refresh_keeps_the_previous_version(server, tmp_path):
    r = _resource(server)
    fetch_resource(tmp_path, "exemplo", r)
    server.files["/a.csv"] = b"versao nova que nao chega inteira\n"
    server.truncated.add("/a.csv")
    with pytest.raises(FetchError):
        fetch_resource(tmp_path, "exemplo", r, refresh=True, backoff=0)
    assert (tmp_path / "exemplo" / "a.csv").read_bytes() == BODY
    assert sorted(p.name for p in (tmp_path / "exemplo").iterdir()) == ["a.csv", "a.csv.meta.json"]


def test_three_attempts_with_growing_wait(server, tmp_path):
    r = _resource(server)
    server.failures["/a.csv"] = 2
    waits = []
    dest = fetch_resource(tmp_path, "exemplo", r, backoff=1.0, sleep=waits.append)
    assert dest.read_bytes() == BODY
    assert waits == [1.0, 2.0]
    assert server.paths() == ["/a.csv"] * 3


def test_gives_up_after_three_attempts(server, tmp_path):
    r = _resource(server)
    server.failures["/a.csv"] = 5
    waits = []
    with pytest.raises(FetchError, match="after 3 attempt.*500"):
        fetch_resource(tmp_path, "exemplo", r, backoff=1.0, sleep=waits.append)
    assert waits == [1.0, 2.0]
    assert len(server.requests) == 3
    assert not (tmp_path / "exemplo" / "a.csv").exists()


def test_default_backoff_is_two_seconds_doubling(server, tmp_path):
    r = _resource(server)
    server.failures["/a.csv"] = 5
    waits = []
    with pytest.raises(FetchError):
        fetch_resource(tmp_path, "exemplo", r, sleep=waits.append)
    assert waits == [2.0, 4.0]


def test_timeout(server, tmp_path):
    r = _resource(server)
    server.slow["/a.csv"] = 1.0
    with pytest.raises(FetchError, match="after 1 attempt"):
        fetch_resource(tmp_path, "exemplo", r, timeout=0.2, attempts=1)
    assert not (tmp_path / "exemplo" / "a.csv").exists()


def _failing(server, path, *codes):
    server.responses[path] = list(codes)
    return _resource(server, path)


@pytest.mark.parametrize("code", [400, 401, 403, 404, 410])
def test_4xx_is_not_retried(server, tmp_path, code):
    r = _failing(server, "/a.csv", code, code, code)
    waits = []
    with pytest.raises(FetchError, match=f"after 1 attempt.*{code}"):
        fetch_resource(tmp_path, "exemplo", r, backoff=1.0, sleep=waits.append)
    assert len(server.requests) == 1
    assert waits == []


@pytest.mark.parametrize("code", [408, 429, 500, 503])
def test_408_429_and_5xx_are_retried(server, tmp_path, code):
    r = _failing(server, "/a.csv", code, code)
    assert fetch_resource(tmp_path, "exemplo", r, backoff=0).read_bytes() == BODY
    assert len(server.requests) == 3


def test_error_other_than_403_has_no_cache_hint(server, tmp_path):
    r = _failing(server, "/a.csv", 404)
    with pytest.raises(FetchError) as e:
        fetch_resource(tmp_path, "exemplo", r, backoff=0)
    assert "browser" not in str(e.value) and "--offline" not in str(e.value)


def test_403_has_the_cache_hint(server, tmp_path):
    r = _failing(server, "/a.csv", 403)
    with pytest.raises(FetchError, match="download the file with a browser") as e:
        fetch_resource(tmp_path, "exemplo", r, backoff=0)
    assert f"save it at {tmp_path / 'exemplo' / 'a.csv'} and rerun with --offline" in str(e.value)


def test_malformed_content_length_is_a_fetch_error(server, tmp_path):
    r = _resource(server)
    server.content_length["/a.csv"] = "abc"
    with pytest.raises(FetchError, match="Content-Length 'abc' is invalid"):
        fetch_resource(tmp_path, "exemplo", r, backoff=0, attempts=1)
    assert list((tmp_path / "exemplo").iterdir()) == []


@pytest.mark.parametrize("n", [0, -1])
def test_attempts_below_one_are_refused(server, tmp_path, n):
    with pytest.raises(ValueError, match="attempts"):
        fetch_resource(tmp_path, "exemplo", _resource(server), attempts=n)
    assert server.requests == []


def test_failed_swap_on_refresh_never_leaves_metadata_describing_another_file(server, tmp_path, monkeypatch):
    """The data file swap fails: the metadata next to it must never describe a file that is not there."""
    import os

    r = _resource(server)
    fetch_resource(tmp_path, "exemplo", r)
    old = (tmp_path / "exemplo" / "a.csv").read_bytes()
    server.files["/a.csv"] = b"versao nova\n"
    real = os.replace

    def fail_on_data_swap(src, dst):
        if os.path.basename(dst) == "a.csv":
            raise OSError("disk full")
        return real(src, dst)

    monkeypatch.setattr("datasettool.sources.cache.os.replace", fail_on_data_swap)
    with pytest.raises(FetchError, match="disk full"):
        fetch_resource(tmp_path, "exemplo", r, refresh=True, attempts=1)
    assert (tmp_path / "exemplo" / "a.csv").read_bytes() == old
    meta = tmp_path / "exemplo" / "a.csv.meta.json"
    assert not meta.exists() or json.loads(meta.read_text(encoding="utf-8"))["sha256"] == hashlib.sha256(old).hexdigest()


# A server answering 200 with an HTML block page instead of the file (dataset-names spec 003e, R4.1) --

CHALLENGE = b"<!DOCTYPE html>\n<html><head><title>Pardon Our Interruption</title></head><body></body></html>\n"


def test_html_page_instead_of_the_file_does_not_enter_the_cache(server, tmp_path):
    resource = _resource(server, body=CHALLENGE)
    server.content_types["/a.csv"] = "text/html; charset=UTF-8"
    with pytest.raises(BlockedError) as e:
        fetch_resource(tmp_path, "exemplo", resource, backoff=0)
    message = str(e.value)
    assert "HTML page (text/html) instead of a.csv" in message
    assert server.url("/a.csv") in message
    assert f"save it at {tmp_path / 'exemplo' / 'a.csv'} and rerun with --offline" in message
    assert server.paths() == ["/a.csv"]
    assert sorted(p.name for p in (tmp_path / "exemplo").iterdir()) == []


def test_html_is_accepted_when_the_resource_is_html(server, tmp_path):
    resource = _resource(server, path="/pagina.html", body=CHALLENGE)
    server.content_types["/pagina.html"] = "Text/HTML"
    assert fetch_resource(tmp_path, "exemplo", resource).read_bytes() == CHALLENGE


def test_csv_served_as_text_csv_is_still_accepted(server, tmp_path):
    resource = _resource(server)
    server.content_types["/a.csv"] = "text/csv; charset=utf-8"
    assert fetch_resource(tmp_path, "exemplo", resource).read_bytes() == BODY


# Path traversal (review of PR #7): source ids and file names never leave the cache --------------

@pytest.mark.parametrize("source_id", ["..", "../x", "a/b", "", ".", "Us-Ssa", "us_ssa", "/etc"])
def test_invalid_source_id_is_refused(tmp_path, source_id):
    with pytest.raises(ValueError, match="source id"):
        cached_path(tmp_path, source_id, "a.csv")


@pytest.mark.parametrize("filename", ["/etc/passwd", "../secret", "a/b.csv", "..", ".hidden", "a.csv.part",
                                      "a.csv.meta.json", "", "a\\b.csv", "a\x00.csv"])
def test_invalid_filename_is_refused(tmp_path, filename):
    with pytest.raises(ValueError, match="file name"):
        cached_path(tmp_path, "src", filename)


def test_offline_fetch_cannot_read_outside_the_cache(server, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    (tmp_path / "secret").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        fetch_resource(cache, "..", Resource(server.url("/secret"), "secret"), offline=True)
    assert server.requests == []


def test_symlinked_source_directory_leaving_the_cache_is_refused(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (cache / "src").symlink_to(outside)
    with pytest.raises(ValueError, match="outside the cache"):
        cached_path(cache, "src", "a.csv")


# Temporary files never follow links (issue #14): R2.5 ---------------------------------------------

def _plant(cache, name, target):
    (cache / "src").mkdir(parents=True, exist_ok=True)
    (cache / "src" / name).symlink_to(target)


def test_planted_part_symlinks_are_not_followed(server, tmp_path):
    cache = tmp_path / "cache"
    outside = tmp_path / "outside"
    outside.mkdir()
    body_target, meta_target = outside / "body", outside / "meta"
    body_target.write_text("KEEP-BODY", encoding="utf-8")
    meta_target.write_text("KEEP-META", encoding="utf-8")
    _plant(cache, "a.csv.part", body_target)
    _plant(cache, "a.csv.meta.json.part", meta_target)
    dest = fetch_resource(cache, "src", _resource(server))
    assert body_target.read_text(encoding="utf-8") == "KEEP-BODY"
    assert meta_target.read_text(encoding="utf-8") == "KEEP-META"
    assert dest.read_bytes() == BODY and not dest.is_symlink()
    meta = dest.with_name("a.csv.meta.json")
    assert not meta.is_symlink() and json.loads(meta.read_text(encoding="utf-8"))["size"] == len(BODY)


def test_dangling_part_symlink_does_not_create_its_target(server, tmp_path):
    cache = tmp_path / "cache"
    target = tmp_path / "outside" / "created"
    target.parent.mkdir()
    _plant(cache, "a.csv.part", target)
    fetch_resource(cache, "src", _resource(server))
    assert not target.exists()


def test_no_temporary_file_is_left_after_success_or_failure(server, tmp_path):
    fetch_resource(tmp_path, "src", _resource(server))
    server.truncated.add("/b.csv")
    bad = _resource(server, "/b.csv")
    with pytest.raises(FetchError):
        fetch_resource(tmp_path, "src", bad, attempts=1)
    assert sorted(p.name for p in (tmp_path / "src").iterdir()) == ["a.csv", "a.csv.meta.json"]
