"""Thin Safaricom Daraja client: STK push (customer pays) and B2C (we pay a customer)."""
import base64
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

import requests
from django.conf import settings
from django.core.cache import cache


class MpesaError(Exception):
    pass


def whole(amount):
    return int(Decimal(str(amount)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class Daraja:
    def __init__(self, env="sandbox", consumer_key="", consumer_secret="", shortcode="", passkey="",
                 initiator_name="", initiator_password=""):
        self.env, self.consumer_key, self.consumer_secret = env, consumer_key, consumer_secret
        self.shortcode, self.passkey = shortcode, passkey
        self.initiator_name, self.initiator_password = initiator_name, initiator_password

    @classmethod
    def from_config(cls, cfg, need="stk"):
        sec = cfg.get_secrets()
        d = cls(cfg.env, sec.get("consumer_key", ""), sec.get("consumer_secret", ""), cfg.shortcode,
                sec.get("passkey", ""), cfg.initiator_name, sec.get("initiator_password", ""))
        d.require(need)
        return d

    @classmethod
    def platform(cls):
        p = settings.MPESA_PLATFORM
        d = cls(p["env"], p["consumer_key"], p["consumer_secret"], p["shortcode"], p["passkey"])
        d.require("stk")
        return d

    def require(self, need):
        miss = [n for n, v in [("consumer key", self.consumer_key), ("consumer secret", self.consumer_secret),
                               ("shortcode", self.shortcode)] if not v]
        if need == "stk" and not self.passkey:
            miss.append("passkey")
        if need == "b2c":
            miss += [n for n, v in [("initiator name", self.initiator_name),
                                    ("initiator password", self.initiator_password)] if not v]
        if miss:
            raise MpesaError("M-Pesa is missing: " + ", ".join(miss) + ".")

    @property
    def base(self):
        return "https://api.safaricom.co.ke" if self.env == "production" else "https://sandbox.safaricom.co.ke"

    def _token(self):
        key = f"daraja:{self.env}:{self.consumer_key}"
        tok = cache.get(key)
        if tok:
            return tok
        try:
            r = requests.get(f"{self.base}/oauth/v1/generate", params={"grant_type": "client_credentials"},
                             auth=(self.consumer_key, self.consumer_secret), timeout=15)
            tok = r.json()["access_token"]
        except Exception:
            raise MpesaError("Could not log in to M-Pesa. Check the consumer key and secret.")
        cache.set(key, tok, 3000)
        return tok

    def _post(self, path, payload):
        try:
            r = requests.post(self.base + path, json=payload, timeout=30,
                              headers={"Authorization": f"Bearer {self._token()}"})
            data = r.json()
        except MpesaError:
            raise
        except Exception:
            raise MpesaError("M-Pesa did not respond. Try again in a moment.")
        if r.status_code >= 400 or str(data.get("ResponseCode", "0")) != "0":
            raise MpesaError(data.get("errorMessage") or data.get("ResponseDescription") or f"M-Pesa error {r.status_code}")
        return data

    def stk_push(self, phone, amount, reference, desc, callback_url):
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        pwd = base64.b64encode(f"{self.shortcode}{self.passkey}{ts}".encode()).decode()
        return self._post("/mpesa/stkpush/v1/processrequest", {
            "BusinessShortCode": self.shortcode, "Password": pwd, "Timestamp": ts,
            "TransactionType": "CustomerPayBillOnline", "Amount": amount, "PartyA": phone,
            "PartyB": self.shortcode, "PhoneNumber": phone, "CallBackURL": callback_url,
            "AccountReference": str(reference)[:12], "TransactionDesc": str(desc)[:13] or "Payment"})

    def security_credential(self):
        from cryptography import x509
        from cryptography.hazmat.primitives.asymmetric import padding
        path = settings.MPESA_CERT_PRODUCTION if self.env == "production" else settings.MPESA_CERT_SANDBOX
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
            try:
                cert = x509.load_pem_x509_certificate(raw)
            except ValueError:
                cert = x509.load_der_x509_certificate(raw)
        except OSError:
            raise MpesaError("The Safaricom certificate file is missing on the server (see backend/dairy/certs).")
        enc = cert.public_key().encrypt(self.initiator_password.encode(), padding.PKCS1v15())
        return base64.b64encode(enc).decode()

    def b2c(self, phone, amount, remarks, result_url, timeout_url, conversation_id, command="BusinessPayment"):
        return self._post("/mpesa/b2c/v3/paymentrequest", {
            "OriginatorConversationID": conversation_id, "InitiatorName": self.initiator_name,
            "SecurityCredential": self.security_credential(), "CommandID": command, "Amount": amount,
            "PartyA": self.shortcode, "PartyB": phone, "Remarks": str(remarks)[:100] or "Payment",
            "QueueTimeOutURL": timeout_url, "ResultURL": result_url, "Occasion": ""})
