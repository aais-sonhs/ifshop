"""
Management command: Fix dữ liệu giá bán lẻ vô lý cho các sản phẩm seed/dev.

Quy tắc:
  - selling_price = 0 → set = import_price * 1.3 (nếu có) hoặc cost_price * 1.5
  - selling_price < import_price → set = import_price * 1.15 (markup 15%)
  - selling_price = 0 và import_price = 0 và cost_price = 0 → giữ nguyên (cần review thủ công)

Sử dụng:
    python manage.py fix_product_pricing          # dry-run
    python manage.py fix_product_pricing --apply  # áp dụng
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal

from products.models import Product


class Command(BaseCommand):
    help = 'Fix dữ liệu giá bán lẻ vô lý: selling_price=0 hoặc selling_price < import_price.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', default=False)
        parser.add_argument(
            '--markup',
            type=float,
            default=1.15,
            help='Markup factor cho sell<imp (default 1.15 = +15%).',
        )
        parser.add_argument(
            '--zero-markup',
            type=float,
            default=1.3,
            help='Markup factor cho sell=0 (default 1.3 = +30%).',
        )

    def _round_price(self, value):
        """Làm tròn lên đến 1,000đ gần nhất để giá đẹp."""
        v = Decimal(str(value)).quantize(Decimal('1'))
        if v <= 0:
            return Decimal('0')
        # Round up to nearest 1000
        thousand = Decimal('1000')
        return ((v + thousand - 1) // thousand) * thousand

    def handle(self, *args, **options):
        apply = options['apply']
        markup = Decimal(str(options['markup']))
        zero_markup = Decimal(str(options['zero_markup']))

        zero_fixes = []
        below_fixes = []
        unfixable = []

        for p in Product.objects.all():
            sp = Decimal(str(p.selling_price or 0))
            ip = Decimal(str(p.import_price or 0))
            cp = Decimal(str(p.cost_price or 0))

            new_sp = None
            if sp <= 0:
                if ip > 0:
                    new_sp = self._round_price(ip * zero_markup)
                elif cp > 0:
                    new_sp = self._round_price(cp * Decimal('1.5'))
                else:
                    unfixable.append(p)
                    continue
                zero_fixes.append((p, sp, new_sp))
            elif ip > 0 and sp < ip:
                new_sp = self._round_price(ip * markup)
                below_fixes.append((p, sp, ip, new_sp))

        self.stdout.write(self.style.WARNING('\n=== KẾT QUẢ QUÉT GIÁ ==='))
        self.stdout.write(f'  selling_price = 0 → fix: {len(zero_fixes)}')
        self.stdout.write(f'  selling_price < import_price → fix: {len(below_fixes)}')
        self.stdout.write(f'  Không fix được (cả 3 trường = 0): {len(unfixable)}')

        if zero_fixes:
            self.stdout.write(self.style.SUCCESS('\n--- selling_price = 0 ---'))
            for p, old, new in zero_fixes[:20]:
                self.stdout.write(f'  [{p.code}] {p.name[:40]}: 0 → {int(new):,}đ')
            if len(zero_fixes) > 20:
                self.stdout.write(f'  ...và {len(zero_fixes) - 20} sản phẩm khác')

        if below_fixes:
            self.stdout.write(self.style.SUCCESS('\n--- selling_price < import_price ---'))
            for p, old, ip, new in below_fixes[:20]:
                self.stdout.write(
                    f'  [{p.code}] {p.name[:40]}: {int(old):,} (imp={int(ip):,}) → {int(new):,}đ'
                )
            if len(below_fixes) > 20:
                self.stdout.write(f'  ...và {len(below_fixes) - 20} sản phẩm khác')

        if unfixable:
            self.stdout.write(self.style.WARNING('\n--- Không fix được (cần review thủ công) ---'))
            for p in unfixable[:20]:
                self.stdout.write(f'  [{p.code}] {p.name[:40]}')

        if not apply:
            self.stdout.write(self.style.NOTICE('\n⚠️  DRY-RUN. Thêm --apply để cập nhật DB.'))
            return

        with transaction.atomic():
            for p, _, new in zero_fixes:
                p.selling_price = new
                p.save(update_fields=['selling_price'])
            for p, _, _, new in below_fixes:
                p.selling_price = new
                p.save(update_fields=['selling_price'])

        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Đã cập nhật {len(zero_fixes) + len(below_fixes)} sản phẩm.'
        ))
