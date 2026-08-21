from django.test import Client, TestCase, override_settings
from django.urls import reverse

from shoppinglist.models import List, ShoppingItem

# SECURE_SSL_REDIRECT is on in real settings (P0-1); the test client talks
# plain HTTP, so every view test here would otherwise get a 301 instead of
# hitting the view. That redirect itself is covered separately in
# test_security.py.
_INSECURE_OK = override_settings(SECURE_SSL_REDIRECT=False)


@_INSECURE_OK
class DestructiveEndpointSafetyTests(TestCase):
    """P0-3: the delete route must never fire on a bare GET."""

    def setUp(self):
        self.shopping_list = List.objects.create(list_name="Groceries")
        self.bought_item = ShoppingItem.objects.create(
            shopping_list=self.shopping_list, item_name="Milk", quantity=1, bought=True
        )

    def test_delete_bought_rejects_get(self):
        url = reverse("shoppinglist:delete", args=[self.shopping_list.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)
        self.assertTrue(ShoppingItem.objects.filter(pk=self.bought_item.pk).exists())

    def test_delete_bought_rejects_post_without_confirmation(self):
        url = reverse("shoppinglist:delete", args=[self.shopping_list.id])
        response = self.client.post(url, {})
        self.assertEqual(response.status_code, 400)
        self.assertTrue(ShoppingItem.objects.filter(pk=self.bought_item.pk).exists())

    def test_delete_bought_requires_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        url = reverse("shoppinglist:delete", args=[self.shopping_list.id])
        response = client.post(url, {"confirm": "yes"})
        self.assertEqual(response.status_code, 403)

    def test_delete_bought_removes_only_bought_items_with_confirmation(self):
        unbought_item = ShoppingItem.objects.create(
            shopping_list=self.shopping_list, item_name="Eggs", quantity=1, bought=False
        )
        url = reverse("shoppinglist:delete", args=[self.shopping_list.id])
        response = self.client.post(url, {"confirm": "yes"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ShoppingItem.objects.filter(pk=self.bought_item.pk).exists())
        self.assertTrue(ShoppingItem.objects.filter(pk=unbought_item.pk).exists())

    def test_update_rejects_get(self):
        url = reverse("shoppinglist:update", args=[self.shopping_list.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)

    def test_add_rejects_get(self):
        url = reverse("shoppinglist:add_item", args=[self.shopping_list.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)


@_INSECURE_OK
class AddItemViewValidationTests(TestCase):
    """P0-4: everything that used to reach SQLite unvalidated."""

    def setUp(self):
        self.shopping_list = List.objects.create(list_name="Groceries")
        self.url = reverse("shoppinglist:add_item", args=[self.shopping_list.id])

    def test_rejects_overlong_item_name(self):
        response = self.client.post(self.url, {"item_name": "A" * 5000, "quantity": 1})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ShoppingItem.objects.count(), 0)

    def test_rejects_non_numeric_quantity(self):
        response = self.client.post(self.url, {"item_name": "Milk", "quantity": "abc"})
        self.assertEqual(response.status_code, 400)

    def test_rejects_negative_quantity(self):
        response = self.client.post(self.url, {"item_name": "Milk", "quantity": -1})
        self.assertEqual(response.status_code, 400)

    def test_rejects_quantity_above_max(self):
        response = self.client.post(self.url, {"item_name": "Milk", "quantity": 999})
        self.assertEqual(response.status_code, 400)

    def test_rejects_blank_name(self):
        response = self.client.post(self.url, {"item_name": "", "quantity": 1})
        self.assertEqual(response.status_code, 400)

    def test_rejects_whitespace_only_name(self):
        response = self.client.post(self.url, {"item_name": "   ", "quantity": 1})
        self.assertEqual(response.status_code, 400)

    def test_missing_fields_returns_400_not_500(self):
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 400)

    def test_enforces_max_items_per_list(self):
        ShoppingItem.objects.bulk_create(
            ShoppingItem(shopping_list=self.shopping_list, item_name=f"item{i}", quantity=1)
            for i in range(200)
        )
        response = self.client.post(self.url, {"item_name": "one too many", "quantity": 1})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            ShoppingItem.objects.filter(shopping_list=self.shopping_list).count(), 200
        )

    def test_accepts_valid_item(self):
        response = self.client.post(self.url, {"item_name": "Milk", "quantity": 2})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ShoppingItem.objects.count(), 1)


@_INSECURE_OK
class UpdateViewExceptionHandlingTests(TestCase):
    """The ValueError escape at the old views.py:25-26 lookup."""

    def setUp(self):
        self.shopping_list = List.objects.create(list_name="Groceries")
        self.other_list = List.objects.create(list_name="Hardware")
        self.item = ShoppingItem.objects.create(
            shopping_list=self.shopping_list, item_name="Milk", quantity=1
        )
        self.other_item = ShoppingItem.objects.create(
            shopping_list=self.other_list, item_name="Nails", quantity=1
        )
        self.url = reverse("shoppinglist:update", args=[self.shopping_list.id])

    def test_update_with_non_numeric_item_id(self):
        response = self.client.post(self.url, {"item": "abc", "update": "1"})
        self.assertEqual(response.status_code, 400)

    def test_update_with_item_id_from_another_list(self):
        response = self.client.post(self.url, {"item": str(self.other_item.id), "update": "1"})
        self.assertEqual(response.status_code, 400)
        self.other_item.refresh_from_db()
        self.assertFalse(self.other_item.bought)

    def test_update_with_no_action_key(self):
        response = self.client.post(self.url, {"item": str(self.item.id)})
        self.assertEqual(response.status_code, 400)

    def test_update_with_both_action_keys(self):
        response = self.client.post(
            self.url, {"item": str(self.item.id), "update": "1", "delete": "1"}
        )
        self.assertEqual(response.status_code, 400)

    def test_update_marks_selected_items_bought(self):
        response = self.client.post(self.url, {"item": str(self.item.id), "update": "1"})
        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        self.assertTrue(self.item.bought)

    def test_update_deletes_selected_items(self):
        response = self.client.post(self.url, {"item": str(self.item.id), "delete": "1"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ShoppingItem.objects.filter(pk=self.item.pk).exists())
