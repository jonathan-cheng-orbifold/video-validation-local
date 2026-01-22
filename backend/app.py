# backend/app.py
#
# Wasabi-backed upload + validation API
# + Super basic auth (single shared passcode) using HttpOnly cookie
#
# Auth requirements implemented:
# - POST /auth/login { secretKey } -> sets HttpOnly cookie if correct
# - POST /auth/logout -> clears cookie
# - All non-auth endpoints require auth (401 if not authed)
# - Secret stored only in env var AUTH_SECRET
# - CORS configured for cookie auth when frontend/backend are on different origins

import base64
import csv
import hashlib
import hmac
import json
import os
import re
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from validator.video_quality_validator import validate_video_file

# ------------------------------------------------------------
# Optional: load .env for local runs
# ------------------------------------------------------------
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except Exception:
    pass

# ------------------------------------------------------------
# Config
# ------------------------------------------------------------

# Wasabi / S3 config
WASABI_BUCKET = os.environ.get("WASABI_BUCKET", "egoexo-val-test")
WASABI_REGION = os.environ.get("WASABI_REGION", "us-east-1")
WASABI_ENDPOINT = os.environ.get("WASABI_ENDPOINT")  # e.g. https://s3.us-east-1.wasabisys.com
WASABI_CREDENTIALS_CSV = os.environ.get("WASABI_CREDENTIALS_CSV")  # path inside container
DEFAULT_SAMPLE_RATE = int(os.environ.get("DEFAULT_SAMPLE_RATE", "30"))

# Auth config (shared secret)
AUTH_SECRET = os.environ.get("AUTH_SECRET")  # REQUIRED
AUTH_COOKIE_NAME = os.environ.get("AUTH_COOKIE_NAME", "egoexo_auth")
AUTH_TTL_SECONDS = int(os.environ.get("AUTH_TTL_SECONDS", "43200"))  # 12h default

# Cookie flags (tune for production)
# - In local http:// dev you usually need SECURE=False
# - In production https:// you should set SECURE=True
AUTH_COOKIE_SECURE = os.environ.get("AUTH_COOKIE_SECURE", "false").lower() == "true"
AUTH_COOKIE_SAMESITE = os.environ.get("AUTH_COOKIE_SAMESITE", "lax").lower()  # "lax" or "none"
AUTH_COOKIE_PATH = "/"

# CORS: MUST NOT be "*" when using cookies; must allow credentials
ALLOWED_ORIGINS = [
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# Key layout
UPLOADS_PREFIX = "uploads"
RECORDS_PREFIX = "records"  # single auxiliary object per upload_id


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_filename_strip_re = re.compile(r"[^A-Za-z0-9._-]+")
_prefix_strip_re = re.compile(r"[^A-Za-z0-9._/-]+")


def safe_filename(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return "upload.bin"
    name = os.path.basename(name)
    name = _filename_strip_re.sub("_", name)
    return name or "upload.bin"


def safe_prefix(prefix: str) -> str:
    prefix = (prefix or "").strip()
    prefix = _prefix_strip_re.sub("_", prefix)
    prefix = prefix.lstrip("/")

    segments = []
    for seg in prefix.split("/"):
        seg = seg.strip()
        if not seg:
            continue
        if seg in (".", ".."):
            continue
        segments.append(seg)
    return "/".join(segments)


def load_wasabi_creds_from_csv(path: str) -> tuple[str, str]:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            access_key = (row.get("Access Key Id") or "").strip()
            secret_key = (row.get("Secret Access Key") or "").strip()
            if access_key and secret_key:
                return access_key, secret_key
    raise RuntimeError("No valid Access Key Id / Secret Access Key found in credentials.csv")


def make_s3_client():
    if not WASABI_ENDPOINT:
        raise RuntimeError("WASABI_ENDPOINT is not set. Example: https://s3.us-east-1.wasabisys.com")
    if not WASABI_CREDENTIALS_CSV:
        raise RuntimeError("WASABI_CREDENTIALS_CSV is not set. It should point to credentials.csv inside the container.")
    access_key, secret_key = load_wasabi_creds_from_csv(WASABI_CREDENTIALS_CSV)
    return boto3.client(
        "s3",
        region_name=WASABI_REGION,
        endpoint_url=WASABI_ENDPOINT,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )


def s3_put_json(bucket: str, key: str, payload: Dict[str, Any]) -> None:
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
    )


def s3_get_json(bucket: str, key: str) -> Dict[str, Any]:
    obj = s3.get_object(Bucket=bucket, Key=key)
    body = obj["Body"].read().decode("utf-8")
    return json.loads(body)


# ------------------------------------------------------------
# Auth token (signed, expiring) stored in HttpOnly cookie
# ------------------------------------------------------------

def _b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("utf-8").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("utf-8"))


def _sign(data: bytes) -> str:
    if not AUTH_SECRET:
        # fail fast if misconfigured
        raise RuntimeError("AUTH_SECRET is not set")
    mac = hmac.new(AUTH_SECRET.encode("utf-8"), data, hashlib.sha256).digest()
    return _b64url_encode(mac)


def make_auth_token() -> str:
    """
    Token format: <payload_b64>.<sig_b64>
    payload JSON: {"exp": <unix seconds>}
    """
    exp = int(time.time()) + AUTH_TTL_SECONDS
    payload = json.dumps({"exp": exp}, separators=(",", ":")).encode("utf-8")
    payload_b64 = _b64url_encode(payload)
    sig_b64 = _sign(payload_b64.encode("utf-8"))
    return f"{payload_b64}.{sig_b64}"


def verify_auth_token(token: str) -> bool:
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        expected = _sign(payload_b64.encode("utf-8"))
        if not hmac.compare_digest(sig_b64, expected):
            return False
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        exp = int(payload.get("exp", 0))
        return time.time() < exp
    except Exception:
        return False


def is_request_authed(request: Request) -> bool:
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        return False
    return verify_auth_token(token)


# ------------------------------------------------------------
# Init clients and app
# ------------------------------------------------------------

# Fail fast if auth not configured
if not AUTH_SECRET:
    raise RuntimeError("AUTH_SECRET env var is required (shared passcode).")

# Init S3 client once
s3 = make_s3_client()

app = FastAPI(title="Ego/Exo Video Validation API", version="0.4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,  # REQUIRED for cookies cross-origin
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ------------------------------------------------------------
# Global auth guard middleware
# ------------------------------------------------------------

AUTH_EXEMPT_PATHS = {
    "/health",
    "/auth/login",
    "/auth/logout",
    "/auth/me",
}

@app.middleware("http")
async def require_auth_middleware(request: Request, call_next):
    # Let CORS preflight through
    if request.method == "OPTIONS":
        return await call_next(request)

    # Exempt auth endpoints + health
    if request.url.path in AUTH_EXEMPT_PATHS:
        return await call_next(request)

    # Everything else requires auth
    if not is_request_authed(request):
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})

    return await call_next(request)


# ------------------------------------------------------------
# Health
# ------------------------------------------------------------

@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "time": utc_now_iso()}


# ------------------------------------------------------------
# Auth endpoints
# ------------------------------------------------------------

class LoginRequest(BaseModel):
    secretKey: str


@app.post("/auth/login")
def login(req: LoginRequest):
    """
    If secretKey matches AUTH_SECRET, set HttpOnly cookie.
    """
    if not req.secretKey or req.secretKey != AUTH_SECRET:
        raise HTTPException(status_code=401, detail="Invalid secret key")

    token = make_auth_token()

    resp = JSONResponse({"ok": True})
    resp.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=AUTH_COOKIE_SECURE,
        samesite=AUTH_COOKIE_SAMESITE,  # "lax" (local) or "none" (cross-site if needed)
        path=AUTH_COOKIE_PATH,
        max_age=AUTH_TTL_SECONDS,
    )
    return resp


@app.post("/auth/logout")
def logout():
    """
    Clear auth cookie.
    """
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(
        key=AUTH_COOKIE_NAME,
        path=AUTH_COOKIE_PATH,
    )
    return resp


@app.get("/auth/me")
def me(request: Request):
    """
    Used by frontend route guard to determine if authenticated.
    """
    return {"authed": is_request_authed(request)}


# ------------------------------------------------------------
# Folder creation
# ------------------------------------------------------------

class CreateFolderRequest(BaseModel):
    parent: str = ""
    name: str


@app.post("/folders")
def create_folder(req: CreateFolderRequest) -> Dict[str, Any]:
    parent = safe_prefix(req.parent)
    name = safe_prefix(req.name)

    if not name:
        raise HTTPException(status_code=400, detail="Invalid folder name")

    folder_key = f"{parent.rstrip('/')}/{name}/" if parent else f"{name}/"

    try:
        s3.put_object(
            Bucket=WASABI_BUCKET,
            Key=folder_key,
            Body=b"",
            ContentType="application/x-directory",
            Metadata={"type": "folder"},
        )
    except (BotoCoreError, ClientError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to create folder: {e}")

    return {"ok": True, "bucket": WASABI_BUCKET, "folder_key": folder_key}


# ------------------------------------------------------------
# Upload + validate
# ------------------------------------------------------------

@app.post("/uploads")
async def upload_video(
    file: UploadFile = File(...),
    folder: str = Form(""),
) -> Dict[str, Any]:
    if not file:
        raise HTTPException(status_code=400, detail="Missing file")

    upload_id = str(uuid.uuid4())
    original_name = safe_filename(file.filename or "video.mp4")

    folder_prefix = safe_prefix(folder).rstrip("/")
    uploads_base = f"{UPLOADS_PREFIX}/{folder_prefix}" if folder_prefix else UPLOADS_PREFIX

    video_key = f"{uploads_base}/{upload_id}_{original_name}"
    record_key = f"{RECORDS_PREFIX}/{upload_id}.json"

    # 1) Buffer upload into a temp file for OpenCV
    tmp_path: Optional[str] = None
    try:
        suffix = Path(original_name).suffix or ".mp4"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = tmp.name
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                tmp.write(chunk)
    except Exception as e:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Failed to buffer upload: {e}")

    # 2) Validate first (on the local temp file)
    try:
        validation = validate_video_file(
            tmp_path,
            sample_rate=DEFAULT_SAMPLE_RATE,
            include_summary=False,
        )
    except Exception as e:
        validation = {
            "passed": False,
            "status": "bad",
            "analyze_success": False,
            "validate_success": False,
            "message": f"Validator crashed: {e}",
            "analyze_message": "",
            "validate_message": "",
            "issues": [f"Validator exception: {e}"],
            "details": {},
            "stats": {},
            "summary": "",
            "video_path": tmp_path,
            "created_at": utc_now_iso(),
        }

    passed = bool(validation.get("passed", False))
    status = "good" if passed else "bad"
    validated_at = utc_now_iso()

    # 3) Upload to Wasabi ONCE with final metadata (no copy_object)
    try:
        from boto3.s3.transfer import TransferConfig  # type: ignore

        transfer_cfg = TransferConfig(
            multipart_threshold=8 * 1024 * 1024,      # 8MB
            multipart_chunksize=64 * 1024 * 1024,     # 64MB parts
            max_concurrency=4,
            use_threads=True,
        )

        extra_args = {
            "ContentType": file.content_type or "application/octet-stream",
            "Metadata": {
                "upload_id": upload_id,
                "filename": original_name,
                "folder": folder_prefix,
                "status": status,
                "passed": "true" if passed else "false",
                "validated_at": validated_at,
                "record_key": record_key,
            },
        }
        
        # multipart + retries for large files
        s3.upload_file(
            Filename=tmp_path,
            Bucket=WASABI_BUCKET,
            Key=video_key,
            ExtraArgs=extra_args,
            Config=transfer_cfg,
        )

    except (BotoCoreError, ClientError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload to Wasabi: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    # 4) Write record JSON after upload
    record = {
        "upload_id": upload_id,
        "bucket": WASABI_BUCKET,
        "folder": folder_prefix,
        "filename": original_name,
        "object_key": video_key,
        "status": status,
        "passed": passed,
        "validated_at": validated_at,
        "validator": {
            "analyze_success": validation.get("analyze_success", False),
            "validate_success": validation.get("validate_success", False),
            "message": validation.get("message", ""),
            "analyze_message": validation.get("analyze_message", ""),
            "validate_message": validation.get("validate_message", ""),
            "issues": validation.get("issues", []),
            "details": validation.get("details", {}),
            "stats": validation.get("stats", {}),
        },
    }

    try:
        s3_put_json(WASABI_BUCKET, record_key, record)
    except (BotoCoreError, ClientError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to write record: {e}")

    return {
        "upload_id": upload_id,
        "filename": original_name,
        "bucket": WASABI_BUCKET,
        "object_key": video_key,
        "folder": folder_prefix,
        "passed": passed,
        "status": status,
        "validated_at": validated_at,
        "record_key": record_key,
        "status_url": f"/status/{upload_id}",
        "issues": record["validator"]["issues"],
        "stats": record["validator"]["stats"],
        "message": record["validator"]["message"],
    }

# ------------------------------------------------------------
# Status
# ------------------------------------------------------------

@app.get("/status/{upload_id}")
def get_status(upload_id: str) -> Dict[str, Any]:
    record_key = f"{RECORDS_PREFIX}/{upload_id}.json"

    # 1) record is the authoritative mapping + details
    try:
        record = s3_get_json(WASABI_BUCKET, record_key)
    except ClientError as e:
        code = (e.response.get("Error") or {}).get("Code")
        if code in ("NoSuchKey", "404", "NotFound"):
            raise HTTPException(status_code=404, detail="Unknown upload_id")
        raise HTTPException(status_code=500, detail=f"Wasabi error reading record: {e}")
    except (BotoCoreError, Exception) as e:
        raise HTTPException(status_code=500, detail=f"Failed to read record: {e}")

    video_key = record.get("object_key")
    if not video_key:
        raise HTTPException(status_code=500, detail="Corrupt record: missing object_key")

    # 2) read video metadata (to keep status in object metadata true)
    meta: Dict[str, str] = {}
    try:
        head = s3.head_object(Bucket=WASABI_BUCKET, Key=video_key)
        meta = head.get("Metadata", {}) or {}
    except Exception:
        meta = {}

    status = (meta.get("status") or record.get("status") or "processing").lower()
    passed_str = meta.get("passed")
    if passed_str == "true":
        passed = True
    elif passed_str == "false":
        passed = False
    else:
        passed = record.get("passed")

    validated_at = meta.get("validated_at") or record.get("validated_at")
    filename = meta.get("filename") or record.get("filename")
    folder = meta.get("folder") or record.get("folder")

    validator = record.get("validator", {}) or {}
    issues = validator.get("issues", []) or []
    stats = validator.get("stats", {}) or {}
    message = validator.get("message", "") or ""

    return {
        "upload_id": upload_id,
        "filename": filename,
        "folder": folder,
        "bucket": WASABI_BUCKET,
        "object_key": video_key,
        "record_key": record_key,
        "status": status,
        "passed": passed,
        "validated_at": validated_at,
        "issues": issues,
        "stats": stats,
        "message": message,
    }
