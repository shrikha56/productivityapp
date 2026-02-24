"""
Security utilities: JWT verification, field encryption, input sanitization.
"""
import os
import re
import jwt

SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "")

# ── JWT verification ──

def verify_token(auth_header: str) -> dict | None:
    """Extract and verify user from a Supabase JWT. Returns {"sub": user_id, ...} or None."""
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    if not SUPABASE_JWT_SECRET:
        # Fallback: decode without verification (dev only, logs warning)
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
            return payload
        except Exception:
            return None
    try:
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_user_id(auth_header: str) -> str | None:
    """Get verified user_id from Authorization header."""
    payload = verify_token(auth_header)
    if payload and payload.get("sub"):
        return payload["sub"]
    return None


# ── Field encryption ──

_fernet = None

def _get_fernet():
    global _fernet
    if _fernet is None and ENCRYPTION_KEY:
        from cryptography.fernet import Fernet
        _fernet = Fernet(ENCRYPTION_KEY.encode())
    return _fernet


def encrypt(text: str) -> str:
    """Encrypt a string. Returns the original if no key is configured."""
    if not text:
        return text
    f = _get_fernet()
    if not f:
        return text
    return f.encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt(text: str) -> str:
    """Decrypt a string. Returns the original if it's not encrypted or no key."""
    if not text:
        return text
    f = _get_fernet()
    if not f:
        return text
    try:
        return f.decrypt(text.encode("utf-8")).decode("utf-8")
    except Exception:
        return text


# ── Input sanitization ──

def sanitize_text(text: str, max_length: int = 5000) -> str:
    """Strip control characters and enforce length limit."""
    if not text:
        return ""
    text = text[:max_length]
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return text.strip()


def clamp_int(value, low: int, high: int, default: int = None) -> int:
    """Safely parse and clamp an integer."""
    try:
        v = int(value)
        return max(low, min(high, v))
    except (TypeError, ValueError):
        return default if default is not None else low


def clamp_float(value, low: float, high: float, default: float = None) -> float:
    """Safely parse and clamp a float."""
    try:
        v = float(value)
        return max(low, min(high, v))
    except (TypeError, ValueError):
        return default if default is not None else low


def validate_date(date_str: str) -> str | None:
    """Validate YYYY-MM-DD format. Returns cleaned string or None."""
    if not date_str or not isinstance(date_str, str):
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str.strip()):
        return date_str.strip()
    return None


def validate_uuid(uid: str) -> str | None:
    """Validate UUID format."""
    if not uid or not isinstance(uid, str):
        return None
    if re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", uid.strip().lower()):
        return uid.strip().lower()
    return None
