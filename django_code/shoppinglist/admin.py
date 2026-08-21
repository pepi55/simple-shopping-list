"""
Admin configuration for shopping list app.

Secured by Django admin authentication (D1 decision).
Additional rate limiting is applied via middleware in settings.py.
"""
from django.contrib import admin

from .models import List, ShoppingItem


class ShoppingItemInline(admin.TabularInline):
    model = ShoppingItem
    extra = 1


class ListAdmin(admin.ModelAdmin):
    fields = ["list_name"]
    inlines = [ShoppingItemInline]
    list_display = ["list_name", "list_size"]


admin.site.register(List, ListAdmin)
