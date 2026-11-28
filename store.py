"""Save the trade journal and risk rules in the GitHub repo, on a separate
'data' branch (so saving never restarts the app or triggers the GitHub job).

Setup: a fine-grained GitHub token with Contents: Read and write on this repo,
added in Streamlit -> Settings -> Secrets:

    [github]
    token = "github_pat_..."
    repo = "anudeep422/market-analyser"   # optional
    branch = "data"                        # optional

Without a token, data is kept only for the current browser session.
"""

from __future__ import annotations

import base64
import io
import json

import pandas as pd
import requests
import streamlit as st

API = "https://api.github.com"
JOURNAL_PATH = "journal/my_trades.csv"
RULES_PATH = "journal/rules.json"


def _cfg() -> dict:
    try:
        g = dict(st.secrets.get("github", {}))
    except Exception:
        g = {}
    return {"token": g.get("token"), "repo": g.get("repo", "anudeep422/market-analyser"),
            "branch": g.get("branch", "data")}


def configured() -> bool:
    return bool(_cfg()["token"])


def _h(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}


def ensure_branch() -> None:
    c = _cfg()
    r = requests.get(f"{API}/repos/{c['repo']}/branches/{c['branch']}", headers=_h(c["token"]), timeout=20)
    if r.status_code == 200:
        return
    if r.status_code != 404:
        raise RuntimeError(f"GitHub error {r.status_code}: {r.text[:200]}")
    base = requests.get(f"{API}/repos/{c['repo']}/git/ref/heads/main", headers=_h(c["token"]), timeout=20)
    base.raise_for_status()
    sha = base.json()["object"]["sha"]
    mk = requests.post(f"{API}/repos/{c['repo']}/git/refs", headers=_h(c["token"]), timeout=20,
                       json={"ref": f"refs/heads/{c['branch']}", "sha": sha})
    if mk.status_code not in (201, 422):     # 422 = created meanwhile
        raise RuntimeError(f"Could not create '{c['branch']}' branch: {mk.text[:200]}")


def read_file(path: str) -> tuple[str | None, str | None]:
    c = _cfg()
    r = requests.get(f"{API}/repos/{c['repo']}/contents/{path}", headers=_h(c["token"]),
                     params={"ref": c["branch"]}, timeout=20)
    if r.status_code == 404:
        return None, None
    if r.status_code != 200:
        raise RuntimeError(f"GitHub error {r.status_code}: {r.text[:200]}")
    d = r.json()
    return base64.b64decode(d["content"]).decode("utf-8"), d["sha"]


def write_file(path: str, text: str, message: str) -> None:
    c = _cfg()
    ensure_branch()
    for attempt in range(2):
        _, sha = read_file(path)
        body = {"message": message, "branch": c["branch"],
                "content": base64.b64encode(text.encode("utf-8")).decode("ascii")}
        if sha:
            body["sha"] = sha
        r = requests.put(f"{API}/repos/{c['repo']}/contents/{path}", headers=_h(c["token"]),
                         json=body, timeout=20)
        if r.status_code in (200, 201):
            return
        if r.status_code in (409, 422) and attempt == 0:
            continue    # someone else wrote meanwhile: re-read sha and retry once
        raise RuntimeError(f"Could not save to GitHub ({r.status_code}): {r.text[:200]}")


# ---------------------------------------------------------- journal/rules

def load_journal() -> pd.DataFrame | None:
    if not configured():
        return st.session_state.get("_journal")
    try:
        text, _ = read_file(JOURNAL_PATH)
    except RuntimeError:
        return st.session_state.get("_journal")
    if not text:
        return None
    return pd.read_csv(io.StringIO(text))


def save_journal(j: pd.DataFrame, message: str = "Update trade journal") -> None:
    st.session_state["_journal"] = j
    if configured():
        write_file(JOURNAL_PATH, j.to_csv(index=False), message)


def load_rules() -> dict | None:
    if not configured():
        return st.session_state.get("_rules")
    try:
        text, _ = read_file(RULES_PATH)
    except RuntimeError:
        return st.session_state.get("_rules")
    return json.loads(text) if text else None


def save_rules(d: dict) -> None:
    st.session_state["_rules"] = d
    if configured():
        write_file(RULES_PATH, json.dumps(d, indent=2), "Update risk rules")
