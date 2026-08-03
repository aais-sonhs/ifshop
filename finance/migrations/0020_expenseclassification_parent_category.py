import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0019_expense_classification'),
    ]

    operations = [
        migrations.AddField(
            model_name='expenseclassification',
            name='parent_category',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='expense_classifications',
                to='finance.financecategory',
                verbose_name='Danh mục cha',
            ),
        ),
    ]
