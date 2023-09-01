from django.urls import path

from . import views

app_name: str = "shoppinglist"

urlpatterns: list = [
        path("", views.index, name = "index"),
        path("<int:list_id>/", views.detail, name = "detail"),
        path("<int:list_id>/update", views.update, name = "update"),
        path("<int:list_id>/delete", views.delete, name = "delete"),
        path("<int:list_id>/add_item", views.add, name = "add_item")
]
