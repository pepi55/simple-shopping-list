from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, HttpRequest, Http404

from .models import List

# TODO: Trans to class based view.

def index(request: HttpRequest) -> HttpResponse:
    shopping_lists: list[List] = List.objects.order_by("-list_name")[:10]
    context = { "shopping_lists": shopping_lists }

    return render(request, "shoppinglist/index.html", context)

def detail(request: HttpRequest, list_id: int) -> HttpResponse:
    shoppinglist: List = get_object_or_404(List, pk = list_id)

    return render(request, "shoppinglist/detail.html", { "shoppinglist": shoppinglist })

def contents(request: HttpRequest, list_id: int) -> HttpResponse:
    return HttpResponse("Display contents of %s." % list_id)
