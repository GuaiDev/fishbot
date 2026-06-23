"""
Simple invite-code auth for FishBot beta.
No email, no OAuth. Generate codes, friends enter them, they get accounts.
"""
import secrets
from datetime import datetime, timedelta

from sqlite_utils import Database


def generate_invite_code(db: Database, created_by: int = 1, note: str = "") -> str:
    """Generate a new invite code. Returns the code string."""
    code = secrets.token_urlsafe(8).upper()
    db["invite_codes"].insert({
        "code": code,
        "created_by": created_by,
        "note": note,
        "is_active": 1,
    })
    db.conn.commit()
    return code


def redeem_invite_code(
    db: Database, code: str, username: str, display_name: str = ""
) -> dict:
    """
    Redeem an invite code and create a user account.
    Returns {"success": True, "token": "...", "user_id": N}
    or {"success": False, "error": "..."}
    """
    code = code.strip().upper()

    invite = next(
        db["invite_codes"].rows_where(
            "code = ? AND is_active = 1 AND used_by IS NULL", [code]
        ),
        None,
    )
    if not invite:
        return {"success": False, "error": "Invalid or already used invite code."}

    existing = next(
        db["users"].rows_where("LOWER(username) = ?", [username.lower()]),
        None,
    )
    if existing:
        return {"success": False, "error": "Username already taken."}

    user_id = db["users"].insert({
        "username": username.lower(),
        "display_name": display_name or username,
        "role": "beta",
        "daily_message_limit": 50,
    }).last_pk

    db["invite_codes"].update(invite["id"], {
        "used_by": user_id,
        "used_at": datetime.now().isoformat(),
        "is_active": 0,
    })
    db.conn.commit()

    token = _create_token(db, user_id)
    return {"success": True, "token": token, "user_id": user_id}


def _create_token(db: Database, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = (datetime.now() + timedelta(days=90)).isoformat()
    db["user_sessions"].insert({
        "user_id": user_id,
        "token": token,
        "expires_at": expires,
        "last_used_at": datetime.now().isoformat(),
    })
    db.conn.commit()
    return token


def get_user_from_token(db: Database, token: str) -> dict | None:
    """
    Validate a session token and return the user dict.
    Returns None if token is invalid or expired.
    """
    if not token:
        return None

    session = next(
        db["user_sessions"].rows_where("token = ?", [token]),
        None,
    )
    if not session:
        return None

    if session.get("expires_at"):
        try:
            expires = datetime.fromisoformat(session["expires_at"])
            if datetime.now() > expires:
                return None
        except Exception:
            pass

    user = next(
        db["users"].rows_where("id = ? AND is_active = 1", [session["user_id"]]),
        None,
    )
    if not user:
        return None

    try:
        db["user_sessions"].update(session["id"], {
            "last_used_at": datetime.now().isoformat()
        })
        db["users"].update(user["id"], {
            "last_seen_at": datetime.now().isoformat()
        })
        db.conn.commit()
    except Exception:
        pass

    return user


def check_rate_limit(db: Database, user_id: int, limit: int = 50) -> dict:
    """
    Check if user has exceeded daily message limit.
    Returns {"allowed": bool, "used": int, "limit": int}
    """
    today = datetime.now().strftime("%Y-%m-%d")
    row = next(
        db["daily_usage"].rows_where(
            "user_id = ? AND date = ?", [user_id, today]
        ),
        None,
    )
    used = row["message_count"] if row else 0
    return {"allowed": used < limit, "used": used, "limit": limit}


def increment_usage(db: Database, user_id: int) -> None:
    """Increment daily message count for a user."""
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        db.execute("""
            INSERT INTO daily_usage (user_id, date, message_count)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, date)
            DO UPDATE SET message_count = message_count + 1
        """, [user_id, today])
        db.conn.commit()
    except Exception:
        pass
