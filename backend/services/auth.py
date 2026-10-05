"""Local authentication and per-request account context."""
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from database import get_db
from models.user import LoginSession, User


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters.")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 390_000)
    return f"pbkdf2_sha256$390000${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        name, iterations, salt, expected = encoded.split("$")
        if name != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


@dataclass
class Identity:
    user: User
    session: LoginSession
    library_user_id: str


DbDep = Annotated[Session, Depends(get_db)]


def current_identity(request: Request, db: DbDep) -> Identity:
    token = request.cookies.get("tracker_session")
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required.")
    row = db.query(LoginSession).filter(LoginSession.token_hash == token_hash(token)).first()
    if not row or row.revoked_at or _aware(row.expires_at) <= utcnow():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired.")
    user = db.get(User, row.user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account unavailable.")
    selected = request.headers.get("X-Library-User")
    if selected and selected != user.id:
        if not user.is_admin or not db.get(User, selected):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Account access denied.")
        return Identity(user, row, selected)
    return Identity(user, row, user.id)


IdentityDep = Annotated[Identity, Depends(current_identity)]


def require_csrf(request: Request, identity: IdentityDep) -> Identity:
    if not hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), identity.session.csrf_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid CSRF token.")
    return identity


MutationDep = Annotated[Identity, Depends(require_csrf)]


def admin_only(identity: IdentityDep) -> Identity:
    if not identity.user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin required.")
    return identity


def owner_id(identity: Identity, requested: str | None = None) -> str:
    if requested and requested != identity.user.id:
        if not identity.user.is_admin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Account access denied.")
        return requested
    return identity.library_user_id


def create_session(db: Session, user: User) -> tuple[str, LoginSession]:
    token = secrets.token_urlsafe(48)
    row = LoginSession(token_hash=token_hash(token), user_id=user.id,
                       csrf_token=secrets.token_urlsafe(32),
                       expires_at=utcnow() + timedelta(days=14), safe_view_enabled=True)
    db.add(row)
    db.commit()
    return token, row
