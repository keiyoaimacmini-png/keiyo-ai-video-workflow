#!/usr/bin/env python3
"""Upload one local completed video to Google Drive from filesystem bytes.

Bytes travel local file -> HTTPS resumable upload. They never enter a chat
message or a tool argument. Stdout never includes access tokens, refresh
tokens, client secrets, or raw Drive IDs.

Runtime OAuth lives only under the gitignored `.runtime/` directory. This
helper does not read host OAuth databases, cookies, or connector secrets.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import os
import re
import secrets
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


HOLD_BYTES = "HOLD_DRIVE_LOCAL_BYTES_UNAVAILABLE"
HOLD_SCOPE = "HOLD_DRIVE_SCOPE_AMBIGUOUS"
HOLD_COLLISION = "HOLD_NAME_COLLISION"
HOLD_UPLOAD = "HOLD_UPLOAD_OUTCOME_UNKNOWN"
OAUTH_SCHEMA = "product_video_drive_upload_oauth.v1"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
TOKEN_URI = "https://oauth2.googleapis.com/token"
AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
UPLOAD_URI = "https://www.googleapis.com/upload/drive/v3/files"
FILES_URI = "https://www.googleapis.com/drive/v3/files"
FOLDER_MIME = "application/vnd.google-apps.folder"
CHUNK_SIZE = 8 * 1024 * 1024
SECRET_RE = re.compile(
    r"(?i)(ya29\.|1//[0-9A-Za-z_-]{8,}|Bearer\s+|refresh_token|client_secret|access_token)"
)
@dataclass
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes


class DriveHttpError(RuntimeError):
    def __init__(self, status: int) -> None:
        super().__init__(f"http_{status}")
        self.status = status


HttpFn = Callable[..., HttpResponse]


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def hold(code: str, reason: str) -> dict[str, str]:
    return {"status": "HOLD", "hold": code, "reason": reason}


FORBIDDEN_OK_KEYS = {"id", "parents", "parent_id", "access_token", "refresh_token", "client_secret"}


def emit(payload: dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if SECRET_RE.search(text) or (payload.get("status") == "OK" and FORBIDDEN_OK_KEYS.intersection(payload)):
        raise ValueError("refusing to print secrets or raw Drive IDs")
    print(text)


def header_map(raw: Any) -> dict[str, str]:
    items = getattr(raw, "items", None)
    if callable(items):
        return {str(key): str(value) for key, value in items()}
    return {}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def http_error_301(self, req, fp, code, msg, headers):  # noqa: N802
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)

    http_error_302 = http_error_303 = http_error_307 = http_error_308 = http_error_301


def default_http(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: float = 30,
) -> HttpResponse:
    request = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            return HttpResponse(response.status, header_map(response.headers), response.read())
    except urllib.error.HTTPError as exc:
        body_bytes = b""
        try:
            body_bytes = exc.read()
        except OSError:
            pass
        if int(exc.code) == 308:
            return HttpResponse(308, header_map(exc.headers), body_bytes)
        raise DriveHttpError(int(exc.code)) from None
    except urllib.error.URLError as exc:
        raise DriveHttpError(0) from exc


def authorized_headers(token: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "product-video-drive-local-upload/1",
        "Accept": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


def json_body(response: HttpResponse) -> dict[str, Any]:
    if not response.body:
        return {}
    data = json.loads(response.body.decode("utf-8"))
    if not isinstance(data, dict):
        raise DriveHttpError(response.status)
    return data


def escape_drive_query(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def load_json_object(path: Path) -> dict[str, Any] | None:
    if path.is_symlink() or not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return None
    return data


def oauth_client_path(project_root: Path) -> Path:
    return project_root / ".runtime" / "drive-oauth-client.json"


def oauth_token_path(project_root: Path) -> Path:
    return project_root / ".runtime" / "drive-upload-oauth.json"


def load_oauth_client(project_root: Path) -> dict[str, str] | None:
    data = load_json_object(oauth_client_path(project_root))
    if data is None:
        return None
    nested = data.get("installed") or data.get("web")
    if isinstance(nested, dict):
        data = nested
    client_id = data.get("client_id")
    if not isinstance(client_id, str) or not client_id.strip():
        return None
    secret = data.get("client_secret")
    return {
        "client_id": client_id.strip(),
        "client_secret": secret.strip() if isinstance(secret, str) else "",
    }


def load_refresh_token(project_root: Path) -> str | None:
    data = load_json_object(oauth_token_path(project_root))
    if data is None:
        return None
    if data.get("schema") != OAUTH_SCHEMA:
        return None
    token = data.get("refresh_token")
    if not isinstance(token, str) or not token.strip():
        return None
    return token.strip()


def store_refresh_token(project_root: Path, refresh_token: str) -> None:
    runtime = project_root / ".runtime"
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = oauth_token_path(project_root)
    payload = {"schema": OAUTH_SCHEMA, "token_uri": TOKEN_URI, "refresh_token": refresh_token}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def refresh_access_token(
    client: dict[str, str],
    refresh_token: str,
    http: HttpFn,
) -> str:
    fields = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client["client_id"],
    }
    if client.get("client_secret"):
        fields["client_secret"] = client["client_secret"]
    response = http(
        "POST",
        TOKEN_URI,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=urllib.parse.urlencode(fields).encode("utf-8"),
        timeout=30,
    )
    data = json_body(response)
    access = data.get("access_token")
    if not isinstance(access, str) or not access:
        raise DriveHttpError(response.status)
    return access


def resolve_access_token(
    project_root: Path,
    *,
    env: dict[str, str],
    http: HttpFn,
) -> str | dict[str, str]:
    env_token = env.get("GOOGLE_DRIVE_ACCESS_TOKEN", "").strip()
    if env_token:
        return env_token
    client = load_oauth_client(project_root)
    refresh = load_refresh_token(project_root)
    if client is None or refresh is None:
        return hold(
            HOLD_BYTES,
            "missing runtime Drive OAuth; operator must place a Desktop OAuth client at "
            ".runtime/drive-oauth-client.json and run this script with --login in Terminal; "
            "do not screenshot Chrome.app; do not inline the video as base64",
        )
    try:
        return refresh_access_token(client, refresh, http)
    except DriveHttpError:
        return hold(HOLD_BYTES, "Drive OAuth refresh failed; operator must rerun --login in Terminal")


def drive_get_json(token: str, url: str, http: HttpFn) -> dict[str, Any]:
    response = http("GET", url, headers=authorized_headers(token), timeout=30)
    if response.status != 200:
        raise DriveHttpError(response.status)
    return json_body(response)


def locate_parent(token: str, parent_title: str, http: HttpFn) -> str | dict[str, str]:
    query = (
        f"mimeType = '{FOLDER_MIME}' and name = '{escape_drive_query(parent_title)}' "
        "and trashed = false"
    )
    params = urllib.parse.urlencode(
        {
            "q": query,
            "pageSize": "10",
            "fields": "files(id,name,mimeType,trashed)",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
    )
    data = drive_get_json(token, f"{FILES_URI}?{params}", http)
    files = data.get("files")
    if not isinstance(files, list):
        return hold(HOLD_SCOPE, "parent folder title must match exactly one Drive folder")
    # Drive name queries are case-insensitive; the product-model folder title is exact.
    exact = [
        row
        for row in files
        if isinstance(row, dict)
        and row.get("name") == parent_title
        and row.get("mimeType") == FOLDER_MIME
        and not row.get("trashed")
        and isinstance(row.get("id"), str)
        and row["id"]
    ]
    if len(exact) != 1:
        return hold(HOLD_SCOPE, "parent folder title must match exactly one Drive folder")
    return exact[0]["id"]


def collision_exists(token: str, parent_id: str, title: str, http: HttpFn) -> bool:
    query = (
        f"name = '{escape_drive_query(title)}' and '{escape_drive_query(parent_id)}' in parents "
        "and trashed = false"
    )
    params = urllib.parse.urlencode(
        {
            "q": query,
            "pageSize": "10",
            "fields": "files(id,name)",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
    )
    data = drive_get_json(token, f"{FILES_URI}?{params}", http)
    files = data.get("files")
    return isinstance(files, list) and len(files) > 0


def start_resumable(
    token: str,
    parent_id: str,
    title: str,
    mime_type: str,
    size: int,
    http: HttpFn,
) -> str:
    metadata = json.dumps(
        {"name": title, "parents": [parent_id], "mimeType": mime_type},
        ensure_ascii=False,
    ).encode("utf-8")
    params = urllib.parse.urlencode(
        {
            "uploadType": "resumable",
            "supportsAllDrives": "true",
            "fields": "id,name,mimeType,size,createdTime",
        }
    )
    response = http(
        "POST",
        f"{UPLOAD_URI}?{params}",
        headers=authorized_headers(
            token,
            {
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": mime_type,
                "X-Upload-Content-Length": str(size),
            },
        ),
        body=metadata,
        timeout=30,
    )
    if response.status not in {200, 201}:
        raise DriveHttpError(response.status)
    location = ""
    for key, value in response.headers.items():
        if key.lower() == "location":
            location = value
            break
    if not location.startswith("https://"):
        raise DriveHttpError(response.status)
    return location


def put_file(token: str, location: str, path: Path, size: int, mime_type: str, http: HttpFn) -> dict[str, Any]:
    sent = 0
    final = HttpResponse(0, {}, b"")
    with path.open("rb") as handle:
        while sent < size:
            chunk = handle.read(min(CHUNK_SIZE, size - sent))
            if not chunk:
                raise DriveHttpError(0)
            start = sent
            end = sent + len(chunk) - 1
            response = http(
                "PUT",
                location,
                headers=authorized_headers(
                    token,
                    {
                        "Content-Type": mime_type,
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {start}-{end}/{size}",
                    },
                ),
                body=chunk,
                timeout=120,
            )
            sent = end + 1
            final = response
            if sent < size and response.status not in {308, 200, 201}:
                raise DriveHttpError(response.status)
    if final.status not in {200, 201}:
        raise DriveHttpError(final.status)
    return json_body(final)


def verify_created(title: str, mime_type: str, size: int, created: dict[str, Any]) -> dict[str, str] | None:
    name = created.get("name")
    mime = created.get("mimeType")
    raw_size = created.get("size")
    created_time = created.get("createdTime")
    if name != title or mime != mime_type:
        return hold(HOLD_UPLOAD, "Drive create read-back name or MIME did not match")
    try:
        if int(str(raw_size)) != size:
            return hold(HOLD_UPLOAD, "Drive create read-back byte size did not match")
    except (TypeError, ValueError):
        return hold(HOLD_UPLOAD, "Drive create read-back byte size did not match")
    if not isinstance(created_time, str) or not created_time:
        return hold(HOLD_UPLOAD, "Drive create read-back time was missing")
    return None


def upload_local_file(
    *,
    project_root: Path,
    local_path: Path,
    title: str,
    mime_type: str,
    parent_title: str,
    env: dict[str, str],
    http: HttpFn,
) -> dict[str, Any]:
    if project_root.is_symlink() or not project_root.is_dir():
        return hold(HOLD_BYTES, "project_root must be a real directory")
    if local_path.is_symlink() or not local_path.is_file():
        return hold(HOLD_BYTES, "local completed video is missing or unsafe")
    if local_path.name != title:
        return hold(HOLD_BYTES, "title must equal the local filename")
    size = local_path.stat().st_size
    if size <= 0:
        return hold(HOLD_BYTES, "local completed video is empty")
    token = resolve_access_token(project_root, env=env, http=http)
    if isinstance(token, dict):
        return token
    try:
        parent = locate_parent(token, parent_title, http)
        if isinstance(parent, dict):
            return parent
        if collision_exists(token, parent, title, http):
            return hold(HOLD_COLLISION, "exact output name already exists in the approved Drive parent")
        location = start_resumable(token, parent, title, mime_type, size, http)
        created = put_file(token, location, local_path, size, mime_type, http)
    except DriveHttpError as exc:
        if exc.status in {401, 403}:
            return hold(HOLD_BYTES, "Drive OAuth cannot create a file in the approved parent")
        if exc.status in {0, 404}:
            return hold(HOLD_SCOPE, "approved Drive parent could not be read")
        return hold(HOLD_UPLOAD, f"Drive resumable upload ended ambiguously ({exc})")
    mismatch = verify_created(title, mime_type, size, created)
    if mismatch is not None:
        return mismatch
    return {
        "status": "OK",
        "title": title,
        "mimeType": mime_type,
        "byteSize": size,
        "sha256": sha256_file(local_path),
        "parent_title": parent_title,
        "createdTime": created["createdTime"],
        "ingest": "local_resumable_upload",
    }


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


class _LoopbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        self.server.auth_code = (query.get("code") or [None])[0]  # type: ignore[attr-defined]
        self.server.auth_error = (query.get("error") or [None])[0]  # type: ignore[attr-defined]
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Drive upload login finished. You can close this window.")

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


def run_login(project_root: Path, *, env: dict[str, str], http_fn: HttpFn) -> dict[str, Any]:
    if not sys.stdin.isatty():
        return hold(
            HOLD_BYTES,
            "run --login in Terminal on this Mac; the agent must not start a browser login",
        )
    client = load_oauth_client(project_root)
    if client is None:
        return hold(
            HOLD_BYTES,
            "place a Google Desktop OAuth client JSON at .runtime/drive-oauth-client.json first",
        )
    verifier, challenge = pkce_pair()
    try:
        server = http.server.HTTPServer(("127.0.0.1", 0), _LoopbackHandler)
    except OSError:
        return hold(HOLD_BYTES, "could not bind loopback for Drive OAuth login")
    server.auth_code = None  # type: ignore[attr-defined]
    server.auth_error = None  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    redirect = f"http://127.0.0.1:{server.server_address[1]}/"
    params = urllib.parse.urlencode(
        {
            "client_id": client["client_id"],
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": DRIVE_SCOPE,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",
        }
    )
    webbrowser.open(f"{AUTH_URI}?{params}", new=1, autoraise=True)
    thread.join(timeout=180)
    server.server_close()
    code = getattr(server, "auth_code", None)
    error = getattr(server, "auth_error", None)
    if error or not isinstance(code, str) or not code:
        return hold(HOLD_BYTES, "Drive OAuth login did not return an authorization code")
    fields = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client["client_id"],
        "redirect_uri": redirect,
        "code_verifier": verifier,
    }
    if client.get("client_secret"):
        fields["client_secret"] = client["client_secret"]
    try:
        response = http_fn(
            "POST",
            TOKEN_URI,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            body=urllib.parse.urlencode(fields).encode("utf-8"),
            timeout=30,
        )
        data = json_body(response)
    except DriveHttpError:
        return hold(HOLD_BYTES, "Drive OAuth code exchange failed")
    refresh = data.get("refresh_token")
    if not isinstance(refresh, str) or not refresh:
        return hold(HOLD_BYTES, "Drive OAuth login did not return a refresh token")
    store_refresh_token(project_root, refresh)
    return {"status": "OK", "login": "stored"}


class _ScriptedHttp:
    def __init__(self, script: list[HttpResponse]) -> None:
        self.script = list(script)
        self.calls: list[tuple[str, str]] = []

    def __call__(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        timeout: float = 30,
    ) -> HttpResponse:
        self.calls.append((method, url))
        if headers and SECRET_RE.search(json.dumps(headers)):
            # Presence on the wire is required; callers must not print it.
            pass
        if not self.script:
            raise DriveHttpError(0)
        return self.script.pop(0)


def self_test() -> int:
    checks: list[tuple[str, bool]] = []

    def check(name: str, ok: bool) -> None:
        checks.append((name, ok))
        if not ok:
            print(f"FAIL {name}", flush=True)

    root = Path(os.environ.get("TMPDIR") or "/tmp") / "drive-local-upload-self-test"
    root.mkdir(parents=True, exist_ok=True)
    video = root / "2026_0906_AN-S182_AI作成①.mp4"
    video.write_bytes(b"fake-mp4-bytes-for-self-test")
    parent_id = "x" * 33
    created = {
        "id": parent_id,
        "name": video.name,
        "mimeType": "video/mp4",
        "size": str(video.stat().st_size),
        "createdTime": "2026-09-06T11:50:29.260Z",
    }
    http = _ScriptedHttp(
        [
            HttpResponse(
                200,
                {},
                json.dumps(
                    {
                        "files": [
                            {
                                "id": parent_id,
                                "name": "AN-S182",
                                "mimeType": FOLDER_MIME,
                                "trashed": False,
                            }
                        ]
                    }
                ).encode("utf-8"),
            ),
            HttpResponse(200, {}, json.dumps({"files": []}).encode("utf-8")),
            HttpResponse(200, {"Location": "https://example.invalid/resume"}, b""),
            HttpResponse(200, {}, json.dumps(created).encode("utf-8")),
        ]
    )
    ok_payload = upload_local_file(
        project_root=root,
        local_path=video,
        title=video.name,
        mime_type="video/mp4",
        parent_title="AN-S182",
        env={"GOOGLE_DRIVE_ACCESS_TOKEN": "ya29.self-test-token"},
        http=http,
    )
    rendered = json.dumps(ok_payload)
    check("upload-ok", ok_payload.get("status") == "OK")
    check("title", ok_payload.get("title") == video.name)
    check("size", ok_payload.get("byteSize") == video.stat().st_size)
    check("no-secret", SECRET_RE.search(rendered) is None)
    check("no-raw-id", parent_id not in rendered)
    check("no-id-field", "id" not in ok_payload)
    check("sha", ok_payload.get("sha256") == sha256_file(video))
    check("ingest-kind", ok_payload.get("ingest") == "local_resumable_upload")
    check("put-called", any(method == "PUT" for method, _ in http.calls))

    missing_auth = upload_local_file(
        project_root=root,
        local_path=video,
        title=video.name,
        mime_type="video/mp4",
        parent_title="AN-S182",
        env={},
        http=_ScriptedHttp([]),
    )
    check("auth-hold", missing_auth.get("hold") == HOLD_BYTES)
    check("auth-no-secret", SECRET_RE.search(json.dumps(missing_auth)) is None)

    colliding = _ScriptedHttp(
        [
            HttpResponse(
                200,
                {},
                json.dumps(
                    {
                        "files": [
                            {
                                "id": parent_id,
                                "name": "AN-S182",
                                "mimeType": FOLDER_MIME,
                                "trashed": False,
                            }
                        ]
                    }
                ).encode("utf-8"),
            ),
            HttpResponse(200, {}, json.dumps({"files": [{"id": "y" * 33, "name": video.name}]}).encode("utf-8")),
        ]
    )
    collision = upload_local_file(
        project_root=root,
        local_path=video,
        title=video.name,
        mime_type="video/mp4",
        parent_title="AN-S182",
        env={"GOOGLE_DRIVE_ACCESS_TOKEN": "ya29.self-test-token"},
        http=colliding,
    )
    check("collision-hold", collision.get("hold") == HOLD_COLLISION)

    ambiguous = upload_local_file(
        project_root=root,
        local_path=video,
        title=video.name,
        mime_type="video/mp4",
        parent_title="AN-S182",
        env={"GOOGLE_DRIVE_ACCESS_TOKEN": "ya29.self-test-token"},
        http=_ScriptedHttp([HttpResponse(200, {}, json.dumps({"files": []}).encode("utf-8"))]),
    )
    check("scope-hold", ambiguous.get("hold") == HOLD_SCOPE)

    mixed_case = locate_parent(
        "ya29.self-test-token",
        "AN-S182",
        _ScriptedHttp(
            [
                HttpResponse(
                    200,
                    {},
                    json.dumps(
                        {
                            "files": [
                                {
                                    "id": "z" * 33,
                                    "name": "an-s182",
                                    "mimeType": FOLDER_MIME,
                                    "trashed": False,
                                },
                                {
                                    "id": parent_id,
                                    "name": "AN-S182",
                                    "mimeType": FOLDER_MIME,
                                    "trashed": False,
                                },
                            ]
                        }
                    ).encode("utf-8"),
                )
            ]
        ),
    )
    check("exact-case-parent", mixed_case == parent_id)

    duplicate_exact = locate_parent(
        "ya29.self-test-token",
        "AN-S182",
        _ScriptedHttp(
            [
                HttpResponse(
                    200,
                    {},
                    json.dumps(
                        {
                            "files": [
                                {
                                    "id": parent_id,
                                    "name": "AN-S182",
                                    "mimeType": FOLDER_MIME,
                                    "trashed": False,
                                },
                                {
                                    "id": "w" * 33,
                                    "name": "AN-S182",
                                    "mimeType": FOLDER_MIME,
                                    "trashed": False,
                                },
                            ]
                        }
                    ).encode("utf-8"),
                )
            ]
        ),
    )
    check("duplicate-exact-scope", isinstance(duplicate_exact, dict) and duplicate_exact.get("hold") == HOLD_SCOPE)

    renamed = upload_local_file(
        project_root=root,
        local_path=video,
        title="other.mp4",
        mime_type="video/mp4",
        parent_title="AN-S182",
        env={"GOOGLE_DRIVE_ACCESS_TOKEN": "ya29.self-test-token"},
        http=_ScriptedHttp([]),
    )
    check("title-mismatch", renamed.get("hold") == HOLD_BYTES)

    login_hold = run_login(root, env={}, http_fn=_ScriptedHttp([]))
    login_src = run_login.__code__.co_varnames
    check("login-requires-tty-or-client", login_hold.get("hold") == HOLD_BYTES)
    check("login-param-is-http-fn", "http_fn" in login_src)
    check("login-param-not-http-module", "http" not in login_src)
    check("login-ok-printable", SECRET_RE.search(json.dumps({"status": "OK", "login": "stored"})) is None)
    check("query-escape", escape_drive_query("A'B") == "A\\'B")
    check("drive-id-not-in-ok-keys", all(key not in {"id", "parents", "parent_id"} for key in ok_payload))

    if not all(ok for _, ok in checks):
        print("SELF-TEST FAILED: upload_drive_local_file", flush=True)
        return 1
    print("SELF-TEST PASSED: upload_drive_local_file")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--local-path", type=Path)
    parser.add_argument("--title")
    parser.add_argument("--mime-type", default="video/mp4")
    parser.add_argument("--parent-title")
    parser.add_argument("--login", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.project_root is None:
        parser.error("--project-root is required unless --self-test is used")
    try:
        if args.login:
            payload = run_login(args.project_root, env=dict(os.environ), http_fn=default_http)
        else:
            if args.local_path is None or args.title is None or args.parent_title is None:
                parser.error("--local-path, --title, and --parent-title are required unless --login or --self-test is used")
            payload = upload_local_file(
                project_root=args.project_root,
                local_path=args.local_path,
                title=args.title,
                mime_type=args.mime_type,
                parent_title=args.parent_title,
                env=dict(os.environ),
                http=default_http,
            )
        emit(payload)
    except (OSError, ValueError, json.JSONDecodeError, DriveHttpError) as exc:
        payload = hold(HOLD_BYTES, str(exc))
        if SECRET_RE.search(json.dumps(payload)):
            payload = hold(HOLD_BYTES, "Drive local ingest failed")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2
    return 0 if payload.get("status") == "OK" else 2


if __name__ == "__main__":
    raise SystemExit(main())
