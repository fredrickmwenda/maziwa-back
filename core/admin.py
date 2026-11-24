from django.contrib import admin


class ReadOnlyAdmin(admin.ModelAdmin):
    """Shown in the admin for inspection but never editable there."""
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False
