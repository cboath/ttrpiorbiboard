#!/usr/bin/env python3
"""One-time interactive login for bambu_printer's cloud mode (params.mode: cloud).

This talks to Bambu's cloud login API, which is unofficial and undocumented
— the request/response shapes below match what several independent
open-source Bambu integrations reverse-engineered, not anything Bambu
publishes. If a step here returns something unexpected, this script prints
the raw response so the flow can be adjusted.

Most accounts require a one-time verification code emailed at login time;
this script requests and prompts for that automatically. If your account
instead uses an authenticator-app code (TFA), that path isn't handled here —
share what the script prints and it can be added.

Usage:
    python3 scripts/bambu_cloud_auth_setup.py
"""
import getpass
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

import requests

from orbiboard.modules.bambu_printer import (
    CLOUD_LOGIN_URL, CLOUD_CODE_URL, CLOUD_CREDENTIALS_FILE,
    _save_cloud_credentials, _jwt_username,
)
from orbiboard.paths import ensure_state_dirs


def main():
    ensure_state_dirs()

    if os.path.exists(CLOUD_CREDENTIALS_FILE):
        print(f"{CLOUD_CREDENTIALS_FILE} already exists. Delete it first if you want to re-authorize.")
        return

    print("\n" + "=" * 60)
    print("  BAMBU CLOUD LOGIN")
    print("=" * 60)
    print("\nUnofficial API — if something below looks wrong, this is where it breaks.\n")

    email = input("Bambu account email: ").strip()
    password = getpass.getpass("Bambu account password: ")

    resp = requests.post(CLOUD_LOGIN_URL, json={"account": email, "password": password}, timeout=15)
    if resp.status_code != 200:
        print(f"Login request failed: {resp.status_code} {resp.text}")
        return
    data = resp.json()
    access_token = data.get("accessToken")
    refresh_token = data.get("refreshToken")

    if not access_token and data.get("loginType") in ("verifyCode", "verify_code"):
        print("\nBambu wants a one-time verification code.")
        code_resp = requests.post(CLOUD_CODE_URL, json={"email": email, "type": "codeLogin"}, timeout=15)
        if code_resp.status_code != 200:
            print(f"Requesting the code failed: {code_resp.status_code} {code_resp.text}")
            return
        print(f"Code sent to {email}.")
        code = input("Enter the code: ").strip()

        resp = requests.post(CLOUD_LOGIN_URL, json={"account": email, "code": code}, timeout=15)
        if resp.status_code != 200:
            print(f"Code login failed: {resp.status_code} {resp.text}")
            return
        data = resp.json()
        access_token = data.get("accessToken")
        refresh_token = data.get("refreshToken")

    if not access_token:
        print("\nLogin did not return an access token. Raw response:")
        print(data)
        print("\nThis usually means Bambu's flow doesn't match what this script")
        print("expects (e.g. TFA instead of an email code) — share this output")
        print("and the script can be adjusted.")
        return

    username = _jwt_username(access_token)
    if not username:
        print("\nWarning: could not decode a 'username' claim from the access token.")
        print("The module needs this to connect — share the token below so the")
        print("claim name can be fixed:")
        print(access_token)

    creds = {
        "accessToken": access_token,
        "refreshToken": refresh_token,
        "expiresAt": int(time.time() * 1000) + data.get("expiresIn", 3600) * 1000,
        "username": username,
    }
    _save_cloud_credentials(creds)
    print(f"\nSaved credentials to {CLOUD_CREDENTIALS_FILE}.")
    print("Set params.mode: cloud for bambu_printer in config/modules.yaml to use it.")


if __name__ == "__main__":
    main()
