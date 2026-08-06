import base64
import hashlib
import json
import time
from pathlib import Path

import pytest

from app import canva
from tests.test_content import SETTINGS


def _settings(tmp_path):
    return SETTINGS.__class__(**{**SETTINGS.__dict__, "token_path": tmp_path / "token.json"})


def test_pkce_pair():
    verifier, challenge = canva.make_pkce()
    assert 43 <= len(verifier) <= 128
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert challenge == expected


def test_auth_url(tmp_path):
    url = canva.build_auth_url(_settings(tmp_path), "chal", "st4te")
    assert url.startswith("https://www.canva.com/api/oauth/authorize?")
    assert "code_challenge=chal" in url
    assert "code_challenge_method=S256" in url
    assert "response_type=code" in url
    assert "client_id=c" in url
    assert "state=st4te" in url
    assert "design%3Acontent%3Awrite" in url or "design:content:write" in url


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeHttp:
    def __init__(self, post_responses=None, get_responses=None):
        self.post_responses = list(post_responses or [])
        self.get_responses = list(get_responses or [])
        self.posts = []
        self.gets = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return self.post_responses.pop(0)

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        return self.get_responses.pop(0)


def _write_token(settings, expires_in=3600):
    settings.token_path.write_text(json.dumps({
        "access_token": "tok", "refresh_token": "ref",
        "expires_at": time.time() + expires_in,
    }))


def test_get_access_token_valid(tmp_path):
    s = _settings(tmp_path)
    _write_token(s)
    assert canva.get_access_token(s, http=FakeHttp()) == "tok"


def test_get_access_token_missing_raises(tmp_path):
    with pytest.raises(canva.NotAuthenticated):
        canva.get_access_token(_settings(tmp_path), http=FakeHttp())


def test_get_access_token_refreshes_expired(tmp_path):
    s = _settings(tmp_path)
    _write_token(s, expires_in=10)
    http = FakeHttp(post_responses=[FakeResponse(200, {
        "access_token": "tok2", "refresh_token": "ref2", "expires_in": 3600, "token_type": "Bearer",
    })])
    assert canva.get_access_token(s, http=http) == "tok2"
    url, kwargs = http.posts[0]
    assert url == "https://api.canva.com/rest/v1/oauth/token"
    assert kwargs["data"]["grant_type"] == "refresh_token"
    saved = json.loads(s.token_path.read_text())
    assert saved["refresh_token"] == "ref2"


def test_import_metadata_title_truncated():
    header = canva._import_metadata("x" * 80)
    meta = json.loads(header)
    assert len(base64.b64decode(meta["title_base64"]).decode()) == 50
    assert meta["mime_type"] == "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def test_import_design_success(tmp_path):
    s = _settings(tmp_path)
    _write_token(s)
    pptx = tmp_path / "p.pptx"
    pptx.write_bytes(b"fake")
    http = FakeHttp(
        post_responses=[FakeResponse(200, {"job": {"id": "j1", "status": "in_progress"}})],
        get_responses=[
            FakeResponse(200, {"job": {"id": "j1", "status": "in_progress"}}),
            FakeResponse(200, {"job": {"id": "j1", "status": "success", "result": {"designs": [
                {"id": "d1", "urls": {"edit_url": "https://canva.com/edit/d1", "view_url": "v"}},
            ]}}}),
        ],
    )
    url = canva.import_design(s, pptx, "My Poster", http=http, poll_interval=0, timeout=5)
    assert url == "https://canva.com/edit/d1"
    post_url, kwargs = http.posts[0]
    assert post_url == "https://api.canva.com/rest/v1/imports"
    assert kwargs["headers"]["Content-Type"] == "application/octet-stream"
    assert "Import-Metadata" in kwargs["headers"]
    assert http.gets[0][0] == "https://api.canva.com/rest/v1/imports/j1"


def test_import_design_failed_job(tmp_path):
    s = _settings(tmp_path)
    _write_token(s)
    pptx = tmp_path / "p.pptx"
    pptx.write_bytes(b"fake")
    http = FakeHttp(post_responses=[FakeResponse(200, {"job": {
        "id": "j1", "status": "failed", "error": {"code": "bad", "message": "nope"},
    }})])
    with pytest.raises(canva.ImportFailed):
        canva.import_design(s, pptx, "t", http=http, poll_interval=0, timeout=5)


def test_import_design_timeout(tmp_path):
    s = _settings(tmp_path)
    _write_token(s)
    pptx = tmp_path / "p.pptx"
    pptx.write_bytes(b"fake")
    stuck_payload = {"job": {"id": "j1", "status": "in_progress"}}

    class InfiniteHttp(FakeHttp):
        def get(self, url, **kwargs):
            self.gets.append((url, kwargs))
            return FakeResponse(200, stuck_payload)

    http = InfiniteHttp(post_responses=[FakeResponse(200, stuck_payload)])
    with pytest.raises(canva.ImportTimeout):
        canva.import_design(s, pptx, "t", http=http, poll_interval=0, timeout=0.1)
