from django.test import TestCase

from shoppinglist.forms import MAX_ITEMS_PER_LIST, AddItemForm, ItemActionForm
from shoppinglist.models import List, ShoppingItem


class AddItemFormTests(TestCase):
    def setUp(self):
        self.shopping_list = List.objects.create(list_name="Groceries")

    def test_rejects_overlong_item_name(self):
        form = AddItemForm(
            {"item_name": "A" * 5000, "quantity": 1}, shopping_list=self.shopping_list
        )
        self.assertFalse(form.is_valid())

    def test_rejects_non_numeric_quantity(self):
        form = AddItemForm(
            {"item_name": "Milk", "quantity": "abc"}, shopping_list=self.shopping_list
        )
        self.assertFalse(form.is_valid())

    def test_rejects_negative_quantity(self):
        form = AddItemForm(
            {"item_name": "Milk", "quantity": -1}, shopping_list=self.shopping_list
        )
        self.assertFalse(form.is_valid())

    def test_rejects_quantity_above_max(self):
        form = AddItemForm(
            {"item_name": "Milk", "quantity": 999}, shopping_list=self.shopping_list
        )
        self.assertFalse(form.is_valid())

    def test_rejects_blank_name(self):
        form = AddItemForm({"item_name": "", "quantity": 1}, shopping_list=self.shopping_list)
        self.assertFalse(form.is_valid())

    def test_rejects_whitespace_only_name(self):
        form = AddItemForm(
            {"item_name": "   ", "quantity": 1}, shopping_list=self.shopping_list
        )
        self.assertFalse(form.is_valid())

    def test_rejects_missing_fields(self):
        form = AddItemForm({}, shopping_list=self.shopping_list)
        self.assertFalse(form.is_valid())

    def test_enforces_max_items_per_list(self):
        ShoppingItem.objects.bulk_create(
            ShoppingItem(shopping_list=self.shopping_list, item_name=f"item{i}", quantity=1)
            for i in range(MAX_ITEMS_PER_LIST)
        )
        form = AddItemForm(
            {"item_name": "one too many", "quantity": 1}, shopping_list=self.shopping_list
        )
        self.assertFalse(form.is_valid())

    def test_accepts_valid_item_and_scopes_it_to_the_list(self):
        form = AddItemForm(
            {"item_name": "Milk", "quantity": 2}, shopping_list=self.shopping_list
        )
        self.assertTrue(form.is_valid())
        item = form.save()
        self.assertEqual(item.shopping_list, self.shopping_list)


class ItemActionFormTests(TestCase):
    def setUp(self):
        self.shopping_list = List.objects.create(list_name="Groceries")
        self.other_list = List.objects.create(list_name="Hardware")
        self.item = ShoppingItem.objects.create(
            shopping_list=self.shopping_list, item_name="Milk", quantity=1
        )
        self.other_item = ShoppingItem.objects.create(
            shopping_list=self.other_list, item_name="Nails", quantity=1
        )

    def test_rejects_non_numeric_item_id(self):
        form = ItemActionForm({"item": ["abc"]}, shopping_list=self.shopping_list)
        self.assertFalse(form.is_valid())

    def test_rejects_item_id_from_another_list(self):
        form = ItemActionForm(
            {"item": [str(self.other_item.id)]}, shopping_list=self.shopping_list
        )
        self.assertFalse(form.is_valid())

    def test_accepts_item_id_scoped_to_the_list(self):
        form = ItemActionForm(
            {"item": [str(self.item.id)]}, shopping_list=self.shopping_list
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(list(form.cleaned_data["item"]), [self.item])
