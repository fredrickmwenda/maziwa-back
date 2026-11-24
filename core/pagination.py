from rest_framework.pagination import LimitOffsetPagination


class Pager(LimitOffsetPagination):
    default_limit = 100
    max_limit = 500
