"""
Management command: Quét tất cả đơn hàng đang ở trạng thái "Đã xuất kho" (status=4)
mà đã thanh toán đủ (payment_status=2) và đã được duyệt (nếu cần) → tự động chuyển
sang "Hoàn thành" (status=5).

Sử dụng:
    python manage.py complete_eligible_orders          # dry-run (chỉ liệt kê)
    python manage.py complete_eligible_orders --apply  # thực thi chuyển trạng thái
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from orders.models import Order


class Command(BaseCommand):
    help = 'Tự động chuyển đơn hàng đủ điều kiện (xuất kho + thanh toán đủ + duyệt) sang Hoàn thành.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            default=False,
            help='Thực sự cập nhật DB. Nếu không có flag này, chỉ liệt kê (dry-run).',
        )

    def handle(self, *args, **options):
        apply = options['apply']

        # Điều kiện: status=4 (Đã xuất kho), payment_status=2 (Đã thanh toán đủ)
        eligible_qs = Order.objects.filter(
            status=4,
            payment_status=2,
        )

        # Loại bỏ đơn cần duyệt mà chưa được duyệt
        orders_to_complete = []
        orders_blocked = []

        for order in eligible_qs.select_related('approver'):
            if order.approver_id and order.approval_status != 2:
                orders_blocked.append(order)
            else:
                orders_to_complete.append(order)

        self.stdout.write(self.style.WARNING(
            f'\n=== KẾT QUẢ QUÉT ĐƠN HÀNG ==='
        ))
        self.stdout.write(f'Tổng đơn ở trạng thái "Đã xuất kho" + "Đã thanh toán đủ": {eligible_qs.count()}')
        self.stdout.write(f'  ✅ Đủ điều kiện hoàn thành: {len(orders_to_complete)}')
        self.stdout.write(f'  ⏳ Chờ duyệt (chưa thể hoàn thành): {len(orders_blocked)}')

        if orders_to_complete:
            self.stdout.write(self.style.SUCCESS('\n--- Đơn đủ điều kiện hoàn thành ---'))
            for o in orders_to_complete:
                self.stdout.write(
                    f'  [{o.code}] Khách: {o.customer} | '
                    f'Tổng: {int(o.final_amount):,}đ | '
                    f'Đã thu: {int(o.paid_amount):,}đ | '
                    f'Ngày: {o.order_date}'
                )

        if orders_blocked:
            self.stdout.write(self.style.WARNING('\n--- Đơn chờ duyệt (không chuyển) ---'))
            for o in orders_blocked:
                approver_name = o.approver.get_full_name() if o.approver else '?'
                self.stdout.write(
                    f'  [{o.code}] Chờ duyệt bởi: {approver_name} | '
                    f'approval_status={o.approval_status}'
                )

        if not apply:
            self.stdout.write(self.style.NOTICE(
                f'\n⚠️  DRY-RUN: Không thay đổi gì. Thêm --apply để thực thi.'
            ))
            return

        # Thực thi chuyển trạng thái
        if not orders_to_complete:
            self.stdout.write('\nKhông có đơn nào cần chuyển.')
            return

        with transaction.atomic():
            ids = [o.id for o in orders_to_complete]
            updated = Order.objects.filter(id__in=ids).update(status=5)

        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Đã chuyển {updated} đơn hàng sang trạng thái "Hoàn thành".'
        ))
