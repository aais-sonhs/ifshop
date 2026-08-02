from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('finance', '0012_alter_payment_options'),
    ]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='approved_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Thời gian duyệt'),
        ),
        migrations.AddField(
            model_name='payment',
            name='approved_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='payments_approved',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Người duyệt',
            ),
        ),
    ]
