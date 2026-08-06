import base64
import hashlib
import json
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode

from app.config import Settings

AUTH_URL = "https://www.canva.com/api/oauth/authorize"
TOKEN_URL = "https://api.canva.com/rest/v1/oauth/token"
IMPORT_URL = "https://api.canva.com/rest/v1/imports"
SCOPE = "design:content:write"
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


class CanvaError(Exception):
    pass


class NotAuthenticated(CanvaError):
    pass


class ImportFailed(CanvaError):
    pass


class ImportTimeout(CanvaError):
    pass


def make_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def build_auth_url(settings: Settings, challenge: str, state: str) -> str:
    query = urlencode({
        "code_challenge": challenge,
        "code_challenge_method": "s256",
        "scope": SCOPE,
        "response_type": "code",
        "client_id": settings.canva_client_id,
        "state": state,
        "redirect_uri": f"{settings.base_url}/auth/canva/callback",
    })
    return f"{AUTH_URL}?{query}"


def _basic_auth(settings: Settings) -> str:
    raw = f"{settings.canva_client_id}:{settings.canva_client_secret}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def _save_token(settings: Settings, payload: dict) -> dict:
    token = {
        "access_token": payload["access_token"],
        "refresh_token": payload["refresh_token"],
        "expires_at": time.time() + float(payload["expires_in"]),
    }
    settings.token_path.write_text(json.dumps(token))
    return token


def _token_request(settings: Settings, data: dict, http=None) -> dict:
    if http is None:
        import httpx
        http = httpx.Client(timeout=30)
    resp = http.post(
        TOKEN_URL,
        headers={
            "Authorization": _basic_auth(settings),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data=data,
    )
    resp.raise_for_status()
    return _save_token(settings, resp.json())


def exchange_code(settings: Settings, code: str, verifier: str, http=None) -> dict:
    return _token_request(settings, {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": verifier,
        "redirect_uri": f"{settings.base_url}/auth/canva/callback",
    }, http=http)


def get_access_token(settings: Settings, http=None) -> str:
    if not settings.token_path.exists():
        raise NotAuthenticated("no token file — connect Canva first")
    token = json.loads(settings.token_path.read_text())
    if token["expires_at"] - time.time() > 60:
        return token["access_token"]
    try:
        refreshed = _token_request(settings, {
            "grant_type": "refresh_token",
            "refresh_token": token["refresh_token"],
        }, http=http)
    except Exception as e:
        raise NotAuthenticated(f"token refresh failed: {e}") from e
    return refreshed["access_token"]


def _import_metadata(title: str) -> str:
    title_b64 = base64.b64encode(title[:50].encode()).decode()
    return json.dumps({"title_base64": title_b64, "mime_type": PPTX_MIME})


def import_design(settings: Settings, pptx: Path, title: str, http=None,
                  poll_interval: float = 2.0, timeout: float = 60.0) -> str:
    if http is None:
        import httpx
        http = httpx.Client(timeout=30)
    access = get_access_token(settings, http=http)
    headers = {
        "Authorization": f"Bearer {access}",
        "Content-Type": "application/octet-stream",
        "Import-Metadata": _import_metadata(title),
    }
    resp = http.post(IMPORT_URL, headers=headers, content=pptx.read_bytes())
    resp.raise_for_status()
    job = resp.json()["job"]
    deadline = time.time() + timeout
    while True:
        if job["status"] == "success":
            return job["result"]["designs"][0]["urls"]["edit_url"]
        if job["status"] == "failed":
            err = job.get("error", {})
            raise ImportFailed(f"{err.get('code')}: {err.get('message')}")
        if time.time() >= deadline:
            raise ImportTimeout(f"import job {job['id']} still in progress after {timeout}s")
        time.sleep(poll_interval)
        poll = http.get(f"{IMPORT_URL}/{job['id']}",
                        headers={"Authorization": f"Bearer {access}"})
        poll.raise_for_status()
        job = poll.json()["job"]
