#!/usr/bin/env python3
"""One-time interactive PKCE OAuth login for the claude_usage module.

Adapted from interactive_auth() in
~/Development/Waveshare-ePaper-10.85-dashboard/claude.py. Run this once
during bring-up (see PRD open question #1) — from the Pi directly if it has
a browser available, or from any machine and then copy the resulting
state/claude_creds.json onto the Pi at the same path. The claude_usage
module only ever refreshes this token afterwards; it never re-prompts.

Usage:
    python3 scripts/claude_auth_setup.py
"""
import base64
import hashlib
import os
import secrets
import sys
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from orbiboard.modules.claude_usage import CLIENT_ID, TOKEN_URL, CREDENTIALS_FILE, _save_credentials
from orbiboard.paths import ensure_state_dirs
import requests
import time

AUTHORIZE_URL = "https://claude.ai/oauth/authorize"
REDIRECT_URI = "http://localhost:18924/callback"
SCOPES = "user:inference user:profile"


def generate_pkce():
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def main():
    ensure_state_dirs()

    if os.path.exists(CREDENTIALS_FILE):
        print(f"{CREDENTIALS_FILE} already exists. Delete it first if you want to re-authorize.")
        return

    verifier, challenge = generate_pkce()
    state = secrets.token_urlsafe(32)

    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    auth_url = AUTHORIZE_URL + "?" + "&".join(f"{k}={v}" for k, v in params.items())

    print("\n" + "=" * 60)
    print("  CLAUDE AI AUTHORIZATION REQUIRED")
    print("=" * 60)
    print("\n1. Open this URL in any browser:\n")
    print(f"   {auth_url}\n")
    print("2. Log in with your Claude account and click Authorize.")
    print("3. You'll land on a dead localhost page — copy the FULL URL")
    print("   from the address bar (it contains ?code=...&state=...).\n")

    callback_url = input("Paste the full callback URL here: ").strip()
    if not callback_url:
        print("Cancelled.")
        return

    parsed = urlparse(callback_url)
    qs = parse_qs(parsed.query)
    code = qs.get("code", [None])[0]
    if not code:
        print("Could not find 'code' in that URL.")
        return

    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier,
        "state": state,
    }
    resp = requests.post(TOKEN_URL, json=payload, timeout=15)
    if resp.status_code != 200:
        print(f"Token exchange failed: {resp.status_code} {resp.text}")
        return

    data = resp.json()
    creds = {
        "accessToken": data.get("access_token"),
        "refreshToken": data.get("refresh_token"),
        "expiresAt": int(time.time() * 1000) + data.get("expires_in", 28800) * 1000,
        "scopes": data.get("scope", SCOPES).split(),
    }
    _save_credentials(creds)
    print(f"\nSaved credentials to {CREDENTIALS_FILE}. The claude_usage module is ready.")


if __name__ == "__main__":
    main()
