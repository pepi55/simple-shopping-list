from django.core.exceptions import ValidationError
from django.test import TestCase

from shoppinglist.models import List, ShoppingItem


class ShoppingItemQuantityValidationTests(TestCase):
    def setUp(self):
        self.shopping_list = List.objects.create(list_name="Groceries")

    def test_quantity_below_minimum_fails_full_clean(self):
        item = ShoppingItem(shopping_list=self.shopping_list, item_name="Milk", quantity=0)
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_quantity_above_maximum_fails_full_clean(self):
        item = ShoppingItem(shopping_list=self.shopping_list, item_name="Milk", quantity=257)
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_quantity_within_bounds_passes_full_clean(self):
        item = ShoppingItem(shopping_list=self.shopping_list, item_name="Milk", quantity=256)
        item.full_clean()
