from .services import client_ip, ctx


class AuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = ctx.set({"ip": client_ip(request), "user": None})
        try:
            return self.get_response(request)
        finally:
            ctx.reset(token)
