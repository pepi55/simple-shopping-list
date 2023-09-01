from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, HttpResponseRedirect, HttpRequest, Http404
from django.urls import reverse

from .models import List, ShoppingItem

# TODO: Trans to class based view.

def index(request: HttpRequest) -> HttpResponse:
    shopping_lists: list[List] = List.objects.order_by("-list_name")[:10]
    context = { "shopping_lists": shopping_lists }

    return render(request, "shoppinglist/index.html", context)

def detail(request: HttpRequest, list_id: int) -> HttpResponse:
    shoppinglist: List = get_object_or_404(List, pk = list_id)

    return render(request, "shoppinglist/detail.html", { "shoppinglist": shoppinglist })

def update(request: HttpRequest, list_id: int) -> HttpResponseRedirect:
    shoppinglist = get_object_or_404(List, pk = list_id)

    for item in request.POST.getlist('item'):
        try:
            selected_item = shoppinglist.shoppingitem_set.get(pk = item)
        except (KeyError, ShoppingItem.DoesNotExist):
            return render(request, "shoppinglist/detail.html", { "shoppinglist": shoppinglist, "error_message": item + " not in list" })
        else:
            if "delete" in request.POST:
                selected_item.delete()
            elif "update" in request.POST:
                selected_item.bought = True
                selected_item.save()

    return HttpResponseRedirect(reverse("shoppinglist:detail", args = [shoppinglist.id]))

def delete(request: HttpRequest, list_id: int) -> HttpResponseRedirect:
    shoppinglist: List = get_object_or_404(List, pk = list_id)

    for item in shoppinglist.shoppingitem_set.filter(bought = True):
        item.delete()

    return HttpResponseRedirect(reverse("shoppinglist:detail", args = [shoppinglist.id]))

def add(request: HttpRequest, list_id: int) -> HttpResponseRedirect:
    shoppinglist: List = get_object_or_404(List, pk = list_id)

    new_item: ShoppingItem = shoppinglist.shoppingitem_set.create(item_name = request.POST["name"], quantity = request.POST["quantity"])

    return HttpResponseRedirect(reverse("shoppinglist:detail", args = [shoppinglist.id]))
