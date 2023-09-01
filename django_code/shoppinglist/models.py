from django.db import models

class List(models.Model):
    list_name: models.CharField = models.CharField("name of list", max_length = 200)

    def list_size(self) -> int:
        return len(self.shoppingitem_set.all())

    def __str__(self) -> str:
        return self.list_name

class ShoppingItem(models.Model):
    shopping_list: models.ForeignKey = models.ForeignKey(List, on_delete = models.CASCADE)
    item_name: models.CharField = models.CharField("item name", max_length = 200)
    quantity: models.IntegerField = models.IntegerField("quantity of item", default = 1)
    bought: models.BooleanField = models.BooleanField("is item bought", default = False)

    def bought_all(self) -> bool:
        return quantity == 0

    def __str__(self) -> str:
        return str(self.quantity) + " " + self.item_name
