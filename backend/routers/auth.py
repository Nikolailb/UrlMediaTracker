"""Local login, one-time invitations, and session safe view."""
import secrets
from datetime import timedelta
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Response, Request, status
from pydantic import BaseModel, Field

from models.user import Invite, User
from services.auth import (DbDep, IdentityDep, MutationDep, create_session,
                           hash_password, owner_id, token_hash, utcnow,
                           verify_password)

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


class AcceptInvite(BaseModel):
    token: str
    username: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=12)


def _session_payload(user: User, session) -> dict:
    return {"id": user.id, "username": user.username, "is_admin": user.is_admin,
            "safe_view_enabled": session.safe_view_enabled, "csrf_token": session.csrf_token}


_login_failures: dict[str, list] = defaultdict(list)


@router.post("/login")
def login(payload: Credentials, response: Response, request: Request, db: DbDep):
    key = f"{request.client.host if request.client else 'unknown'}:{payload.username}"
    now = utcnow()
    _login_failures[key] = [at for at in _login_failures[key] if (now - at).total_seconds() < 300]
    if len(_login_failures[key]) >= 5:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Try again later.")
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not user.is_active or not verify_password(payload.password, user.hashed_password):
        _login_failures[key].append(now)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials.")
    _login_failures.pop(key, None)
    token, session = create_session(db, user)
    response.set_cookie("tracker_session", token, httponly=True,
                        secure=request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https",
                        samesite="strict", max_age=14 * 86400, path="/")
    return _session_payload(user, session)


@router.get("/me")
def me(identity: IdentityDep):
    return _session_payload(identity.user, identity.session)


@router.post("/logout")
def logout(response: Response, identity: MutationDep, db: DbDep):
    identity.session.revoked_at = utcnow()
    db.commit()
    response.delete_cookie("tracker_session", path="/")
    return {"ok": True}


@router.post("/safe-view")
def safe_view(enabled: bool, identity: MutationDep, db: DbDep):
    identity.session.safe_view_enabled = enabled
    db.commit()
    return {"safe_view_enabled": enabled}


@router.post("/invites")
def create_invite(identity: MutationDep, db: DbDep):
    if not identity.user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin required.")
    token = secrets.token_urlsafe(32)
    db.add(Invite(token_hash=token_hash(token), created_by=identity.user.id,
                  expires_at=utcnow() + timedelta(hours=24)))
    db.commit()
    return {"token": token, "expires_in_hours": 24}


@router.post("/accept-invite")
def accept_invite(payload: AcceptInvite, response: Response, request: Request, db: DbDep):
    invite = db.query(Invite).filter(Invite.token_hash == token_hash(payload.token)).first()
    if not invite or invite.used_at or invite.expires_at.replace(tzinfo=invite.expires_at.tzinfo or utcnow().tzinfo) <= utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invite invalid or expired.")
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Username exists.")
    updated = db.query(Invite).filter(Invite.id == invite.id, Invite.used_at.is_(None)).update({"used_at": utcnow()})
    if updated != 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invite already used.")
    user = User(username=payload.username, hashed_password=hash_password(payload.password))
    db.add(user)
    db.commit()
    token, session = create_session(db, user)
    response.set_cookie("tracker_session", token, httponly=True,
                        secure=request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https",
                        samesite="strict", max_age=14 * 86400, path="/")
    return _session_payload(user, session)


@router.get("/users")
def users(identity: IdentityDep, db: DbDep):
    if not identity.user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin required.")
    return [{"id": u.id, "username": u.username, "is_active": u.is_active}
            for u in db.query(User).order_by(User.username).all()]
