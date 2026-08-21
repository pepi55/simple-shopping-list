from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_POST, require_safe
from django_ratelimit.decorators import ratelimit

from .forms import AddItemForm, ItemActionForm
from .models import List

# TODO: Trans to class based view.

WRITE_RATE = "20/m"
DESTROY_RATE = "5/m"


def ratelimited_view(request: HttpRequest, exception=None) -> HttpResponse:
    return HttpResponse("Too many requests.", status = 429)


@require_safe
def index(request: HttpRequest) -> HttpResponse:
    shopping_lists: list[List] = List.objects.order_by("-list_name")[:10]
    context = { "shopping_lists": shopping_lists }

    return render(request, "shoppinglist/index.html", context)

@require_safe
def detail(request: HttpRequest, list_id: int) -> HttpResponse:
    shoppinglist: List = get_object_or_404(List, pk = list_id)
    add_form = AddItemForm(shopping_list = shoppinglist)

    return render(request, "shoppinglist/detail.html", { "shoppinglist": shoppinglist, "add_form": add_form })

@require_POST
@ratelimit(key = "ip", rate = WRITE_RATE, method = "POST", block = True)
def update(request: HttpRequest, list_id: int) -> HttpResponse:
    shoppinglist = get_object_or_404(List, pk = list_id)

    form = ItemActionForm(request.POST, shopping_list = shoppinglist)
    if not form.is_valid():
        return HttpResponseBadRequest("invalid item selection")

    is_update = "update" in request.POST
    is_delete = "delete" in request.POST
    if is_update == is_delete:
        return HttpResponseBadRequest("exactly one of update or delete is required")

    items = form.cleaned_data["item"]
    if is_delete:
        items.delete()
    else:
        items.update(bought = True)

    return HttpResponseRedirect(reverse("shoppinglist:detail", args = [shoppinglist.id]))

@require_POST
@ratelimit(key = "ip", rate = DESTROY_RATE, method = "POST", block = True)
def delete(request: HttpRequest, list_id: int) -> HttpResponse:
    shoppinglist: List = get_object_or_404(List, pk = list_id)

    if request.POST.get("confirm") != "yes":
        return HttpResponseBadRequest("confirmation required")

    shoppinglist.shoppingitem_set.filter(bought = True).delete()

    return HttpResponseRedirect(reverse("shoppinglist:detail", args = [shoppinglist.id]))

@require_POST
@ratelimit(key = "ip", rate = WRITE_RATE, method = "POST", block = True)
def add(request: HttpRequest, list_id: int) -> HttpResponse:
    shoppinglist: List = get_object_or_404(List, pk = list_id)

    form = AddItemForm(request.POST, shopping_list = shoppinglist)
    if not form.is_valid():
        return HttpResponseBadRequest(form.errors.as_text())

    form.save()

    return HttpResponseRedirect(reverse("shoppinglist:detail", args = [shoppinglist.id]))
