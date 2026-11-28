import base64
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import store as ST  # noqa: E402


class Resp:
    def __init__(self, code, data=None):
        self.status_code, self._d = code, data or {}
        self.text = str(data)

    def json(self):
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeGitHub:
    """Minimal in-memory GitHub contents API."""

    def __init__(self, has_branch=False):
        self.files, self.branches, self.calls = {}, {"main"} | ({"data"} if has_branch else set()), []

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append(("GET", url))
        assert headers["Authorization"] == "Bearer T"
        if "/branches/" in url:
            return Resp(200 if url.rsplit("/", 1)[1] in self.branches else 404)
        if "/git/ref/heads/main" in url:
            return Resp(200, {"object": {"sha": "abc"}})
        path = url.split("/contents/")[1]
        assert params["ref"] == "data"
        if path not in self.files:
            return Resp(404)
        text, sha = self.files[path]
        return Resp(200, {"content": base64.b64encode(text.encode()).decode(), "sha": sha})

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append(("POST", url))
        self.branches.add(json["ref"].split("/")[-1])
        return Resp(201)

    def put(self, url, headers=None, json=None, timeout=None):
        self.calls.append(("PUT", url))
        path = url.split("/contents/")[1]
        assert json["branch"] == "data"
        if path in self.files:
            assert json.get("sha") == self.files[path][1]
        n = len(self.calls)
        self.files[path] = (base64.b64decode(json["content"]).decode(), f"sha{n}")
        return Resp(201)


@pytest.fixture
def gh(monkeypatch):
    fake = FakeGitHub()
    monkeypatch.setattr(ST, "_cfg", lambda: {"token": "T", "repo": "u/r", "branch": "data"})
    monkeypatch.setattr(ST.requests, "get", fake.get)
    monkeypatch.setattr(ST.requests, "post", fake.post)
    monkeypatch.setattr(ST.requests, "put", fake.put)
    return fake


def test_creates_branch_and_roundtrips_journal(gh):
    assert ST.load_journal() is None
    j = pd.DataFrame({"id": [1], "Symbol": ["INFY"], "PnL": [12.5]})
    ST.save_journal(j)
    assert "data" in gh.branches and ("POST", "https://api.github.com/repos/u/r/git/refs") in gh.calls
    back = ST.load_journal()
    assert back.iloc[0]["Symbol"] == "INFY" and back.iloc[0]["PnL"] == 12.5
    j2 = pd.concat([j, pd.DataFrame({"id": [2], "Symbol": ["TCS"], "PnL": [-3.0]})])
    ST.save_journal(j2)                     # update needs the existing sha
    assert len(ST.load_journal()) == 2


def test_rules_roundtrip(gh):
    assert ST.load_rules() is None
    ST.save_rules({"capital": 50000})
    assert ST.load_rules() == {"capital": 50000}


def test_no_token_uses_session(monkeypatch):
    monkeypatch.setattr(ST, "_cfg", lambda: {"token": None, "repo": "u/r", "branch": "data"})
    assert not ST.configured()
    called = []
    monkeypatch.setattr(ST.requests, "put", lambda *a, **k: called.append(1))
    ST.save_journal(pd.DataFrame({"id": [1]}))
    assert ST.load_journal()["id"].tolist() == [1]
    assert not called
