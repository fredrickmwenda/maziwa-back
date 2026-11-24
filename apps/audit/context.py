"""Per-request audit context. No imports beyond the stdlib on purpose —
anything that wants to *read* the caller's user/ip imports from here,
not from services.py, so the audit chain can never create a cycle."""
import contextvars

ctx = contextvars.ContextVar("audit_ctx", default=None)
