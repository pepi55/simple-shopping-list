from django import forms

from .models import ShoppingItem

MAX_ITEMS_PER_LIST = 200


class AddItemForm(forms.ModelForm):
    class Meta:
        model = ShoppingItem
        fields = ["item_name", "quantity"]
        widgets = {
            "quantity": forms.NumberInput(attrs={"style": "width: 3em;"}),
        }

    def __init__(self, *args, shopping_list, **kwargs):
        super().__init__(*args, **kwargs)
        self.shopping_list = shopping_list

    def clean_item_name(self):
        # The length check SQLite will NOT enforce for you.
        name = self.cleaned_data["item_name"].strip()
        if not name:
            raise forms.ValidationError("Item name is required.")
        return name

    def clean(self):
        cleaned = super().clean()
        if self.shopping_list.shoppingitem_set.count() >= MAX_ITEMS_PER_LIST:
            raise forms.ValidationError(f"This list is full (max {MAX_ITEMS_PER_LIST} items).")
        return cleaned

    def save(self, commit=True):
        item = super().save(commit=False)
        item.shopping_list = self.shopping_list
        if commit:
            item.save()
        return item


class ItemActionForm(forms.Form):
    """Validates and scopes the item IDs submitted by detail.html."""

    item = forms.ModelMultipleChoiceField(queryset=ShoppingItem.objects.none())

    def __init__(self, *args, shopping_list, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].queryset = shopping_list.shoppingitem_set.all()
