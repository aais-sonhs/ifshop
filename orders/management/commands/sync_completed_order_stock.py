"""
Management command: Đồng bộ tồn kho cho các đơn đã ở trạng thái xuất kho/hoàn thành
nhưng tồn kho chưa được trừ (do được sửa trực tiếp trên DB hoặc do sự cố).

Lệnh này quét các đơn ở status 4 (Đã xuất kho) hoặc 5 (Hoàn thành), so sánh tồn kho
hiện tại với log lịch sử để xác định đơn nào chưa được trừ tồn, và trừ tồn cho chúng.

Vì không có cờ riêng đánh dấu "đã trừ tồn", lệnh dùng tham số --orders để truyền
trực tiếp danh sách mã đơn cần đồng bộ.

Sử dụng:
    python manage.py sync_completed_order_stock --orders DH-021,DH-022 --apply
    python manage.py sync_completed_order_stock --orders DH-021                # dry-run
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal

from orders.models import Order
from products.models import ProductStock, ComboItem


class Command(BaseCommand):
    help = 'Trừ tồn kho cho đơn đã hoàn thành/xuất kho mà tồn chưa giảm.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--orders',
            type=str,
            required=True,
            help='Danh sách mã đơn cần đồng bộ tồn (ví dụ: DH-021,DH-022).',
        )
        parser.add_argument(
            '--apply',
            action='store_true',
            default=False,
            help='Thực sự trừ tồn. Mặc định chỉ in ra dự kiến.',
        )

    def _calc_deltas(self, order):
        """Trả về dict {(product_id, warehouse_id): delta_to_subtract}."""
        deltas = {}
        if not order.warehouse_id:
            return deltas
        wid = order.warehouse_id

        for item in order.items.select_related('product').all():
            product = item.product
            if not product or product.is_service:
                continue
            qty = Decimal(str(item.quantity or 0))

            if product.is_combo:
                for ci in ComboItem.objects.filter(combo_id=product.id).select_related('product'):
                    if ci.product.is_service:
                        continue
                    sub_qty = qty * Decimal(str(ci.quantity or 0))
                    key = (ci.product_id, wid)
                    deltas[key] = deltas.get(key, Decimal('0')) + sub_qty
            else:
                key = (product.id, wid)
                deltas[key] = deltas.get(key, Decimal('0')) + qty
        return deltas

    def handle(self, *args, **options):
        codes = [c.strip() for c in options['orders'].split(',') if c.strip()]
        apply = options['apply']

        orders = Order.objects.filter(code__in=codes)
        found_codes = {o.code for o in orders}
        missing = set(codes) - found_codes
        if missing:
            self.stdout.write(self.style.ERROR(
                f'Không tìm thấy đơn: {", ".join(sorted(missing))}'
            ))

        all_deltas = {}  # (product_id, warehouse_id) -> total delta across orders
        per_order_deltas = []

        for order in orders:
            if order.status not in (4, 5):
                self.stdout.write(self.style.WARNING(
                    f'Bỏ qua [{order.code}]: status={order.status} không phải 4/5.'
                ))
                continue
            if not order.warehouse_id:
                self.stdout.write(self.style.WARNING(
                    f'Bỏ qua [{order.code}]: chưa gán kho xuất.'
                ))
                continue

            deltas = self._calc_deltas(order)
            per_order_deltas.append((order, deltas))
            for k, v in deltas.items():
                all_deltas[k] = all_deltas.get(k, Decimal('0')) + v

        if not per_order_deltas:
            self.stdout.write('Không có đơn nào cần xử lý.')
            return

        # In ra kế hoạch
        self.stdout.write(self.style.WARNING('\n=== KẾ HOẠCH TRỪ TỒN ==='))
        for order, deltas in per_order_deltas:
            self.stdout.write(f'\n[{order.code}] Kho ID={order.warehouse_id}')
            for (pid, wid), qty in deltas.items():
                stock = ProductStock.objects.filter(product_id=pid, warehouse_id=wid).first()
                cur = stock.quantity if stock else Decimal('0')
                new_q = cur - qty
                marker = '⚠️  ÂM' if new_q < 0 else ''
                self.stdout.write(
                    f'  product_id={pid}: tồn hiện tại={cur} → trừ {qty} → còn {new_q} {marker}'
                )

        if not apply:
            self.stdout.write(self.style.NOTICE(
                '\n⚠️  DRY-RUN. Thêm --apply để thực thi.'
            ))
            return

        # Apply
        with transaction.atomic():
            for (pid, wid), total_qty in all_deltas.items():
                stock, _ = ProductStock.objects.select_for_update().get_or_create(
                    product_id=pid,
                    warehouse_id=wid,
                    defaults={'quantity': 0},
                )
                stock.quantity = Decimal(str(stock.quantity or 0)) - total_qty
                stock.save(update_fields=['quantity'])

        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Đã trừ tồn cho {len(per_order_deltas)} đơn.'
        ))
