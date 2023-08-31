from django.urls import path

from . import views

app_name: str = "shoppinglist"

urlpatterns: list = [
        path("", views.index, name = "index"),
        path("<int:list_id>/", views.detail, name = "detail"),
        path("<int:list_id>/contents", views.contents, name = "contents"),
]
