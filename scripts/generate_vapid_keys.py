"""One-off: generate a VAPID keypair for Web Push and print .env-ready lines.

    python scripts/generate_vapid_keys.py
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid02


def main() -> None:
    vapid = Vapid02()
    vapid.generate_keys()

    # py_vapid stores an EC keypair; re-encode as the url-safe base64 that the
    # Web Push spec (and pywebpush, and browsers' applicationServerKey) expect.
    public_raw = vapid.public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    private_raw = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")

    public_b64 = base64.urlsafe_b64encode(public_raw).rstrip(b"=").decode()
    private_b64 = base64.urlsafe_b64encode(private_raw).rstrip(b"=").decode()

    print(f"VAPID_PUBLIC_KEY={public_b64}")
    print(f"VAPID_PRIVATE_KEY={private_b64}")
    print("VAPID_SUBJECT=mailto:you@example.com")


if __name__ == "__main__":
    main()
