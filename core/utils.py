"""Phone normalisation and field encryption shared by every app."""
import base64
import hashlib
import json
import re

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def normalize_phone(raw):
    """Any common Kenyan format -> 2547XXXXXXXX / 2541XXXXXXXX."""
    d = re.sub(r"\D", "", str(raw or ""))
    if len(d) == 10 and d[0] == "0":
        d = "254" + d[1:]
    elif len(d) == 9 and d[0] in "17":
        d = "254" + d
    if not re.fullmatch(r"254[17]\d{8}", d):
        raise ValueError("Enter a valid Kenyan phone number, e.g. 0712345678.")
    return d


def _fernet():
    key = settings.FIELD_ENCRYPTION_KEY or base64.urlsafe_b64encode(
        hashlib.sha256(settings.SECRET_KEY.encode()).digest()).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_json(data):
    return _fernet().encrypt(json.dumps(data).encode()).decode()


def decrypt_json(token):
    if not token:
        return {}
    try:
        return json.loads(_fernet().decrypt(token.encode()).decode())
    except (InvalidToken, ValueError):
        return {}
