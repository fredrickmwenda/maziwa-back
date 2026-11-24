from django.contrib import admin
from apps.accounts.models import AccountSecurity, Membership, Role

admin.site.register(Role)
admin.site.register(Membership)
admin.site.register(AccountSecurity)
