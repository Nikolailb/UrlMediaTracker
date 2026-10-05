"""Local, interactive first-admin bootstrap and password recovery.

Run after Alembic migration: python -m admin_bootstrap --username admin
"""
import argparse
import getpass
import sys

from database import SessionLocal
from models.item import TrackedItem
from models.user import User, LoginSession
from services.auth import hash_password, utcnow


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password-stdin", action="store_true")
    args = parser.parse_args()
    password = sys.stdin.readline().rstrip("\r\n") if args.password_stdin else getpass.getpass("New admin password (12+ characters): ")
    confirm = password if args.password_stdin else getpass.getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("Passwords do not match.")
    encoded = hash_password(password)
    with SessionLocal() as db:
        first_admin = not db.query(User).filter(User.is_admin.is_(True)).first()
        user = db.query(User).filter(User.username == args.username).first()
        if not user:
            user = User(username=args.username)
            db.add(user)
            db.flush()
        user.hashed_password = encoded
        user.is_admin = True
        user.is_active = True
        if first_admin:
            db.query(TrackedItem).update({"user_id": user.id})
        db.query(LoginSession).filter(LoginSession.user_id == user.id).update({"revoked_at": utcnow()})
        db.commit()
        print("Admin ready. Legacy items assigned on first bootstrap.")


if __name__ == "__main__":
    main()
