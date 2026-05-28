from django.db import migrations


def enable_product_images_for_quotation_templates(apps, schema_editor):
    PrintTemplate = apps.get_model('system_management', 'PrintTemplate')
    PrintTemplate.objects.filter(
        template_type__in=['quotation', 'quotation_a4'],
        show_product_images=False,
    ).update(show_product_images=True)


class Migration(migrations.Migration):

    dependencies = [
        ('system_management', '0016_printtemplate_show_combo_components'),
    ]

    operations = [
        migrations.RunPython(
            enable_product_images_for_quotation_templates,
            migrations.RunPython.noop,
        ),
    ]
