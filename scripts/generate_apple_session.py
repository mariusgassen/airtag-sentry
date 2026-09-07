"""One-off: log in to Apple ID via FindMy.py on *this* machine and write an
account.json session file, for uploading through the dashboard's Settings ->
Apple-Konten -> "Session-Datei hochladen" option.

Fallback for when the live login inside the app's own container keeps
failing with `findmy.errors.UnhandledProtocolError: Error response for GSA
request: 503` - a raw rejection from Apple's own GrandSlam-auth endpoint.
Running the handshake from a different machine changes both the source IP
(a home/residential connection instead of wherever the container is hosted)
and gets a completely fresh anisette device identity - either of which may
be what's tripping Apple's abuse detection. See tasks/roadmap.md #12.

    pip install findmy
    python scripts/generate_apple_session.py
"""

from __future__ import annotations

import getpass
import json

from findmy import (
    AppleAccount,
    LocalAnisetteProvider,
    LoginState,
    SmsSecondFactorMethod,
    TrustedDeviceSecondFactorMethod,
)


def _describe(method) -> str:
    if isinstance(method, TrustedDeviceSecondFactorMethod):
        return "Trusted device"
    if isinstance(method, SmsSecondFactorMethod):
        return f"SMS ({method.phone_number})"
    return "Unknown method"


def main() -> None:
    email = input("Apple ID: ").strip()
    password = getpass.getpass("Password: ")

    account = AppleAccount(LocalAnisetteProvider())
    state = account.login(email, password)

    if state == LoginState.REQUIRE_2FA:
        methods = account.get_2fa_methods()
        for i, method in enumerate(methods):
            print(f"  [{i}] {_describe(method)}")
        index = int(input("Choose a method: ").strip() or "0")
        chosen = methods[index]
        chosen.request()
        code = input("2FA code: ").strip()
        chosen.submit(code)

    account.to_json("account.json")
    print("\nWrote account.json - upload it via Settings > Apple-Konten in the dashboard.")


if __name__ == "__main__":
    main()
