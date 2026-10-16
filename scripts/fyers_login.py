"""Generate a local FYERS access token for the read-only connection check.

The App Secret and authorization code are entered with hidden input and are
never written to disk or printed. The returned access token is saved to the
ignored local .env file for the FastAPI process.
"""

from __future__ import annotations

import getpass
import os
import re
import tempfile
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"


def _write_env(updates: dict[str, str]) -> None:
    if not ENV_FILE.exists():
        ENV_FILE.write_text(ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")

    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    remaining = dict(updates)
    output: list[str] = []
    for line in lines:
        match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if match and match.group(1) in remaining:
            key = match.group(1)
            output.append(f"{key}={remaining.pop(key)}")
        else:
            output.append(line)
    output.extend(f"{key}={value}" for key, value in remaining.items())

    handle, temporary_name = tempfile.mkstemp(prefix=".env-", dir=ROOT, text=True)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as temporary:
            temporary.write("\n".join(output) + "\n")
        if os.name != "nt":
            os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, ENV_FILE)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _extract_auth_code(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if "://" in value:
        query = parse_qs(urlsplit(value).query)
        return query.get("auth_code", [""])[0].strip()
    return value


def main() -> int:
    try:
        from fyers_apiv3 import fyersModel  # type: ignore[import-not-found]
    except ImportError:
        print('FYERS SDK missing. Install it with: .\\.venv\\Scripts\\python.exe -m pip install -e ".[fyers]"')
        return 1

    app_id = input("FYERS App ID: ").strip()
    app_secret = getpass.getpass("New FYERS App Secret (hidden): ").strip()
    redirect_uri = input("Registered FYERS redirect URL (exact match): ").strip()
    if not app_id or not app_secret or not redirect_uri:
        print("App ID, App Secret, and registered redirect URL are required.")
        return 1

    try:
        session = fyersModel.SessionModel(
            client_id=app_id,
            redirect_uri=redirect_uri,
            response_type="code",
            grant_type="authorization_code",
            state="mayur-algo-local",
            scope="",
            nonce="",
        )
        login_url = session.generate_authcode()
    except Exception:
        print("Could not create the FYERS login URL. Check the App ID and redirect URL.")
        return 1

    print("Opening FYERS login. Complete the FYERS sign-in and daily verification in your browser.")
    if not webbrowser.open(login_url, new=1):
        print(f"Open this login URL in your browser:\n{login_url}")
    pasted = getpass.getpass("Paste the auth_code value or the full redirected URL (hidden): ")
    auth_code = _extract_auth_code(pasted)
    if not auth_code:
        print("No auth_code was found. Run the login helper again and use the URL from the redirect.")
        return 1

    try:
        token_session = fyersModel.SessionModel(
            client_id=app_id,
            secret_key=app_secret,
            grant_type="authorization_code",
        )
        token_session.set_token(auth_code)
        response = token_session.generate_token()
    except Exception:
        print("FYERS token exchange failed. Check the fresh secret, auth code, and redirect URL; response was not logged.")
        return 1

    if isinstance(response, dict):
        token = response.get("access_token")
        if response.get("s") == "error" or not isinstance(token, str):
            print("FYERS did not return an access token. Check the login and app details; response was not logged.")
            return 1
    elif isinstance(response, str):
        token = response
    else:
        print("FYERS returned an unexpected token response; response was not logged.")
        return 1

    token = token.strip()
    if not token or any(char in token for char in "\r\n"):
        print("FYERS returned an invalid access token; it was not saved.")
        return 1

    _write_env(
        {
            "NIFTY_ALGO_FYERS_APP_ID": app_id,
            "NIFTY_ALGO_FYERS_ACCESS_TOKEN": token,
            "NIFTY_ALGO_FYERS_READONLY_ENABLED": "true",
        }
    )
    # Avoid retaining credentials longer than required in local references.
    app_secret = ""
    auth_code = ""
    token = ""
    print("Access token saved to the ignored local .env file. Restart FastAPI, then click Check connection.")
    print("This only enables the project's read-only FYERS connection check; it does not place trades.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
