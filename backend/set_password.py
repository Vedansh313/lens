"""Set a user's password from the command line (Phase 5, step 1).

    python set_password.py alice@example.com --generate
    python set_password.py alice@example.com --prompt
    python set_password.py alice@example.com --stdin < secret.txt

Deliberately a command-line tool and NOT an API endpoint, for the same reason
promote_admin.py is: a route that overwrites a password without knowing the old
one is the last thing that should be reachable over the network. Changing a
password requires shell access to the machine running the database.

THIS IS THE ONLY WAY TO CHANGE A PASSWORD IN PHASE 5. Self-service reset needs a
transactional email provider, which was deferred to Phase 6, so a user who
forgets their password cannot recover the account without an operator running
this. That is a known gap, not an oversight - see PHASE5.md.

Output is deliberately ASCII-only: this runs on a server console, and Windows
terminals default to cp1252, where a non-ASCII character renders as a replacement
glyph in the middle of a security instruction.

--generate is the recommended form: it prints a password from secrets.choice and
never takes one from the shell. Passwords typed as arguments end up in shell
history and in `ps` output for every user on the box, so there is deliberately
no --password flag.

Run it from the backend/ directory so `db`, `models` and `security` resolve.
"""
from __future__ import annotations

import argparse
import getpass
import secrets
import string
import sys

from sqlalchemy import select

from db import SessionLocal
from models import User
from security import hash_password

# Backend rule is 8 (auth.py RegisterIn). This tool is for operator-set
# passwords on privileged accounts, so it asks for more.
MIN_LENGTH = 12
GENERATED_LENGTH = 24

# Ambiguous glyphs removed: a generated password gets read off a screen and
# retyped at least once, and 0/O and 1/l/I are where that goes wrong.
_ALPHABET = (
    "".join(c for c in string.ascii_letters if c not in "lIO")
    + "".join(c for c in string.digits if c not in "01")
    + "!@#$%^&*-_=+?"
)


def generate_password(length: int = GENERATED_LENGTH) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Set a Lens account's password.")
    parser.add_argument("email", help="email address of the account to change")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--generate", action="store_true",
                        help="generate a strong password and print it once (recommended)")
    source.add_argument("--prompt", action="store_true",
                        help="prompt for a password without echoing it")
    source.add_argument("--stdin", action="store_true",
                        help="read the password from stdin (for scripted provisioning)")
    args = parser.parse_args(argv)

    if args.generate:
        password = generate_password()
    elif args.prompt:
        password = getpass.getpass("New password: ")
        if password != getpass.getpass("Repeat: "):
            print("Passwords did not match.", file=sys.stderr)
            return 1
    else:
        password = sys.stdin.readline().rstrip("\n")

    if not args.generate and len(password) < MIN_LENGTH:
        print(f"Password must be at least {MIN_LENGTH} characters.", file=sys.stderr)
        return 1

    email = args.email.strip().lower()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            print(f"No account with email {email!r}.", file=sys.stderr)
            return 1

        user.password_hash = hash_password(password)
        db.commit()

        print(f"Password updated for {user.email} (id {user.id}"
              f"{', admin' if user.is_admin else ''}).")
        if args.generate:
            # Printed once and never stored anywhere. There is no recovery flow
            # in Phase 5, so losing this means running this tool again.
            print(f"\n    {password}\n")
            print("Store it in a password manager now - it is not saved anywhere,")
            print("and there is no self-service reset until Phase 6.")

        # Existing tokens keep working: JWTs are stateless and carry only the
        # user id, so nothing about them is invalidated by a password change.
        # Rotating JWT_SECRET is what ends every session, and that is a separate
        # operation with a much wider blast radius.
        print("\nNote: sessions already signed in are NOT ended by this change.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
