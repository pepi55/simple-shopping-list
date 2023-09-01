from django.contrib import admin

from .models import List, ShoppingItem

class ShoppingItemInline(admin.TabularInline):
    model = ShoppingItem
    extra = 1

class ListAdmin(admin.ModelAdmin):
    fields: list = [ "list_name" ]
    inlines: list = [ ShoppingItemInline ]
    list_display: list = [ "list_name", "list_size" ]

admin.site.register(List, ListAdmin)
