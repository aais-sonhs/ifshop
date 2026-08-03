import django.db.models.deletion
from django.db import migrations, models


def _single(values):
    values = list(dict.fromkeys(value for value in values if value))
    return values[0] if len(values) == 1 else None


def backfill_finance_brand_scope(apps, schema_editor):
    Brand = apps.get_model('system_management', 'Brand')
    FinancialPlan = apps.get_model('finance', 'FinancialPlan')
    FinanceCategory = apps.get_model('finance', 'FinanceCategory')
    CashBook = apps.get_model('finance', 'CashBook')
    Receipt = apps.get_model('finance', 'Receipt')
    Payment = apps.get_model('finance', 'Payment')
    FinancialPlanItem = apps.get_model('finance', 'FinancialPlanItem')
    SupplierPaymentSchedule = apps.get_model('finance', 'SupplierPaymentSchedule')

    company_brand_ids = list(
        Brand.objects.filter(brand_type='company').values_list('id', flat=True)
    )
    only_company_brand_id = company_brand_ids[0] if len(company_brand_ids) == 1 else None

    for plan in FinancialPlan.objects.filter(brand_id__isnull=True).select_related(
        'store', 'created_by__profile__store',
    ):
        brand_id = plan.store.brand_id if plan.store_id else None
        if not brand_id and plan.created_by_id:
            try:
                brand_id = plan.created_by.profile.store.brand_id
            except Exception:
                brand_id = None
            if not brand_id:
                brand_id = _single(
                    Brand.objects.filter(
                        owner_id=plan.created_by_id,
                        brand_type='company',
                    ).values_list('id', flat=True)
                )
        plan.brand_id = brand_id or only_company_brand_id
        if plan.brand_id:
            plan.save(update_fields=['brand'])

    for category in FinanceCategory.objects.filter(brand_id__isnull=True):
        related_brand_ids = list(
            Receipt.objects.filter(category_id=category.id, store_id__isnull=False)
            .values_list('store__brand_id', flat=True)
        )
        related_brand_ids += list(
            Receipt.objects.filter(category_id=category.id, order__store_id__isnull=False)
            .values_list('order__store__brand_id', flat=True)
        )
        related_brand_ids += list(
            Payment.objects.filter(category_id=category.id, store_id__isnull=False)
            .values_list('store__brand_id', flat=True)
        )
        related_brand_ids += list(
            Payment.objects.filter(
                category_id=category.id,
                goods_receipt__warehouse__store_id__isnull=False,
            ).values_list('goods_receipt__warehouse__store__brand_id', flat=True)
        )
        related_brand_ids += list(
            FinancialPlanItem.objects.filter(category_id=category.id, plan__brand_id__isnull=False)
            .values_list('plan__brand_id', flat=True)
        )
        category.brand_id = _single(related_brand_ids) or only_company_brand_id
        if category.brand_id:
            category.save(update_fields=['brand'])

    for cashbook in CashBook.objects.filter(brand_id__isnull=True):
        related_brand_ids = list(
            Receipt.objects.filter(cash_book_id=cashbook.id, store_id__isnull=False)
            .values_list('store__brand_id', flat=True)
        )
        related_brand_ids += list(
            Receipt.objects.filter(cash_book_id=cashbook.id, order__store_id__isnull=False)
            .values_list('order__store__brand_id', flat=True)
        )
        related_brand_ids += list(
            Payment.objects.filter(cash_book_id=cashbook.id, store_id__isnull=False)
            .values_list('store__brand_id', flat=True)
        )
        related_brand_ids += list(
            Payment.objects.filter(
                cash_book_id=cashbook.id,
                goods_receipt__warehouse__store_id__isnull=False,
            ).values_list('goods_receipt__warehouse__store__brand_id', flat=True)
        )
        related_brand_ids += list(
            FinancialPlanItem.objects.filter(cash_book_id=cashbook.id, plan__brand_id__isnull=False)
            .values_list('plan__brand_id', flat=True)
        )
        related_brand_ids += list(
            SupplierPaymentSchedule.objects.filter(
                cash_book_id=cashbook.id,
                plan__brand_id__isnull=False,
            ).values_list('plan__brand_id', flat=True)
        )
        cashbook.brand_id = _single(related_brand_ids) or only_company_brand_id
        if cashbook.brand_id:
            cashbook.save(update_fields=['brand'])


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0017_advanced_financial_planning'),
        ('system_management', '0026_serviceprice_billing_month'),
    ]

    operations = [
        migrations.AddField(
            model_name='financecategory',
            name='brand',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='finance_categories',
                to='system_management.brand',
                verbose_name='Thương hiệu',
            ),
        ),
        migrations.AddField(
            model_name='cashbook',
            name='brand',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='cash_books',
                to='system_management.brand',
                verbose_name='Thương hiệu',
            ),
        ),
        migrations.AddField(
            model_name='financialplan',
            name='brand',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='financial_plans',
                to='system_management.brand',
                verbose_name='Thương hiệu',
            ),
        ),
        migrations.RunPython(backfill_finance_brand_scope, migrations.RunPython.noop),
    ]
