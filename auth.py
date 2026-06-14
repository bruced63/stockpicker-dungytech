# auth.py — User management for StockPicker

import json
import os
from datetime import date
from werkzeug.security import generate_password_hash, check_password_hash

USERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.json")


def load_users():
    if not os.path.exists(USERS_FILE):
        return []
    with open(USERS_FILE) as f:
        return json.load(f)


def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


def get_user(username):
    return next((u for u in load_users() if u["username"] == username), None)


def verify_password(username, password):
    u = get_user(username)
    return u is not None and check_password_hash(u["password_hash"], password)


def create_user(username, password, role="user", email=""):
    users = load_users()
    if any(u["username"] == username for u in users):
        return False, "Username already exists."
    users.append({
        "username": username,
        "password_hash": generate_password_hash(password),
        "role": role,
        "email": email,
        "created_at": str(date.today()),
    })
    save_users(users)
    return True, f'User "{username}" created.'


def set_password(username, new_password):
    users = load_users()
    for u in users:
        if u["username"] == username:
            u["password_hash"] = generate_password_hash(new_password)
            save_users(users)
            return True
    return False


def delete_user(username):
    users = [u for u in load_users() if u["username"] != username]
    save_users(users)


def init_default_admin():
    """Create a default admin account if no users exist yet."""
    if not load_users():
        create_user(
            "admin", "DungyTech2026!",
            role="admin", email="bruce.dungy@dungytech.com"
        )
        return True
    return False
