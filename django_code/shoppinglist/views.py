"""
Shopping list views.

These views are intentionally unauthenticated (no login_required) per
decision D1 in the security plan. The app is served publicly over the
internet, and shopping-list views are intentionally world-accessible.

CSRF protection is added via @csrf_protect decorator where appropriate.
"""
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseForbidden
from django.views.decorators.csrf import csrf_protect
from django.urls import reverse

from .models import List, ShoppingItem

# TODO: Trans to class based view.


def index(request):
    """Display all shopping lists.

    This view is intentionally unauthenticated per decision D1.
    """
    shopping_lists = List.objects.order_by("-list_name")[:10]
    context = {"shopping_lists": shopping_lists}

    return render(request, "shoppinglist/index.html", context)


@csrf_protect
def detail(request, list_id):
    """Display a single shopping list.

    This view is intentionally unauthenticated per decision D1.
    """
    shoppinglist = get_object_or_404(List, pk=list_id)

    return render(request, "shoppinglist/detail.html", {"shoppinglist": shoppinglist})


@csrf_protect
def update(request, list_id):
    """Update items in a shopping list.

    This view is intentionally unauthenticated per decision D1.
    Only allows POST requests with CSRF protection.
    """
    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")

    shoppinglist = get_object_or_404(List, pk=list_id)

    for item in request.POST.getlist("item"):
        try:
            selected_item = shoppinglist.shoppingitem_set.get(pk=item)
        except (KeyError, ShoppingItem.DoesNotExist):
            return render(request, "shoppinglist/detail.html", {
                "shoppinglist": shoppinglist,
                "error_message": item + " not in list"
            })
        else:
            if "delete" in request.POST:
                selected_item.delete()
            elif "update" in request.POST:
                selected_item.bought = True
                selected_item.save()

    return HttpResponseRedirect(reverse("shoppinglist:detail", args=[shoppinglist.id]))


@csrf_protect
def delete(request, list_id):
    """Delete all bought items in a shopping list.

    This view is intentionally unauthenticated per decision D1.
    Only allows POST requests with CSRF protection.
    """
    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")

    shoppinglist = get_object_or_404(List, pk=list_id)

    for item in shoppinglist.shoppingitem_set.filter(bought=True):
        item.delete()

    return HttpResponseRedirect(reverse("shoppinglist:detail", args=[shoppinglist.id]))


@csrf_protect
def add(request, list_id):
    """Add a new item to a shopping list.

    This view is intentionally unauthenticated per decision D1.
    Only allows POST requests with CSRF protection.
    """
    if request.method != "POST":
        return HttpResponseForbidden("Method not allowed")

    shoppinglist = get_object_or_404(List, pk=list_id)

    # Validate inputs
    item_name = request.POST.get("name")
    quantity = request.POST.get("quantity")

    if not item_name or not quantity:
        return render(request, "shoppinglist/detail.html", {
            "shoppinglist": shoppinglist,
            "error_message": "Missing required fields"
        })

    try:
        quantity = int(quantity)
        if quantity <= 0:
            return render(request, "shoppinglist/detail.html", {
                "shoppinglist": shoppinglist,
                "error_message": "Invalid quantity"
            })
    except (ValueError, TypeError):
        return render(request, "shoppinglist/detail.html", {
            "shoppinglist": shoppinglist,
            "error_message": "Invalid quantity"
        })

    new_item = shoppinglist.shoppingitem_set.create(
        item_name=item_name,
        quantity=quantity
    )

    return HttpResponseRedirect(reverse("shoppinglist:detail", args=[shoppinglist.id]))
