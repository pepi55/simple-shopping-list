# Generated manually to add server-side bounds on ShoppingItem.quantity (P0-4)

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('shoppinglist', '0002_alter_shoppingitem_bought'),
    ]

    operations = [
        migrations.AlterField(
            model_name='shoppingitem',
            name='quantity',
            field=models.IntegerField(
                default=1,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(256),
                ],
                verbose_name='quantity of item',
            ),
        ),
    ]
