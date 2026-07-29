"""Grant or revoke the admin flag on a user account (Phase 4).

Deliberately a command-line tool and NOT an API endpoint: a self-serve route
that grants admin rights is the one thing that must not be reachable over the
network, however well guarded. Promotion requires shell access to the machine
running the database.

    python promote_admin.py --list
    python promote_admin.py alice@example.com
    python promote_admin.py alice@example.com --revoke

Run it from the backend/ directory so `db` and `models` resolve.
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from db import SessionLocal
from models import User


def _print_admins(db) -> None:
    admins = db.scalars(select(User).where(User.is_admin).order_by(User.id)).all()
    if not admins:
        print("No admin users. Promote one with: python promote_admin.py <email>")
        return
    print(f"{len(admins)} admin user(s):")
    for u in admins:
        print(f"  #{u.id}  {u.email}  ({u.name})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Grant or revoke Lens admin rights.")
    parser.add_argument("email", nargs="?", help="email address of the account to change")
    parser.add_argument("--revoke", action="store_true", help="remove admin rights instead")
    parser.add_argument("--list", action="store_true", help="list current admins and exit")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        if args.list or not args.email:
            _print_admins(db)
            # No email is not an error when the user only wanted the listing.
            return 0 if args.list else 1

        email = args.email.strip().lower()
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            print(f"No account with email {email!r}.", file=sys.stderr)
            return 1

        target = not args.revoke
        if user.is_admin == target:
            print(f"{user.email} is already {'an admin' if target else 'a regular user'}.")
            return 0

        # Refuse to remove the last admin — that would lock every admin route
        # behind a shell command nobody remembers exists.
        if args.revoke:
            remaining = db.scalar(
                select(User).where(User.is_admin, User.id != user.id).limit(1)
            )
            if remaining is None:
                print(
                    f"Refusing to revoke: {user.email} is the only admin. "
                    "Promote someone else first.",
                    file=sys.stderr,
                )
                return 1

        user.is_admin = target
        db.commit()
        print(f"{user.email} is now {'an admin' if target else 'a regular user'}.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
