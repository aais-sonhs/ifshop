"""
Management command: Đồng bộ trạng thái đơn hàng theo quy trình thống nhất.

Quy tắc:
  - Đơn ở "Báo giá" (status=0) mà đã có thanh toán + không cần duyệt (hoặc đã duyệt)
    → tự promote sang "Đơn hàng" (status=1).
  - Đơn ở "Đã xuất kho" (status=4) mà đã thanh toán đủ + (đã duyệt nếu cần)
    → tự promote sang "Hoàn thành" (status=5).

Sử dụng:
    python manage.py complete_eligible_orders          # dry-run (chỉ liệt kê)
    python manage.py complete_eligible_orders --apply  # thực thi chuyển trạng thái
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from orders.models import Order


class Command(BaseCommand):
    help = 'Đồng bộ trạng thái đơn hàng: Báo giá→Đơn hàng khi có thanh toán, Xuất kho→Hoàn thành khi đủ điều kiện.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            default=False,
            help='Thực sự cập nhật DB. Nếu không có flag này, chỉ liệt kê (dry-run).',
        )

    def handle(self, *args, **options):
        apply = options['apply']

        # ========== PHASE 1: Báo giá (0) → Đơn hàng (1) khi đã có thanh toán ==========
        promote_to_order_qs = Order.objects.filter(
            status=0,
            paid_amount__gt=0,
        ).select_related('approver')

        orders_to_promote = []
        orders_pending_approval = []
        for order in promote_to_order_qs:
            if order.approver_id and order.approval_status != 2:
                orders_pending_approval.append(order)
            else:
                orders_to_promote.append(order)

        # ========== PHASE 2: Xuất kho (4) → Hoàn thành (5) ==========
        complete_qs = Order.objects.filter(
            status=4,
            payment_status=2,
        ).select_related('approver')

        orders_to_complete = []
        orders_blocked_by_approval = []
        for order in complete_qs:
            if order.approver_id and order.approval_status != 2:
                orders_blocked_by_approval.append(order)
            else:
                orders_to_complete.append(order)

        # ========== Báo cáo ==========
        self.stdout.write(self.style.WARNING('\n=== KẾT QUẢ QUÉT ĐƠN HÀNG ==='))
        self.stdout.write(f'\n[1] Báo giá → Đơn hàng (đã có thanh toán):')
        self.stdout.write(f'    ✅ Đủ điều kiện: {len(orders_to_promote)}')
        self.stdout.write(f'    ⏳ Chờ duyệt: {len(orders_pending_approval)}')

        self.stdout.write(f'\n[2] Đã xuất kho → Hoàn thành (đã thanh toán đủ):')
        self.stdout.write(f'    ✅ Đủ điều kiện: {len(orders_to_complete)}')
        self.stdout.write(f'    ⏳ Chờ duyệt: {len(orders_blocked_by_approval)}')

        if orders_to_promote:
            self.stdout.write(self.style.SUCCESS('\n--- Đơn promote Báo giá → Đơn hàng ---'))
            for o in orders_to_promote:
                self.stdout.write(
                    f'  [{o.code}] {o.customer} | '
                    f'Tổng: {int(o.final_amount):,}đ | Đã thu: {int(o.paid_amount):,}đ'
                )

        if orders_to_complete:
            self.stdout.write(self.style.SUCCESS('\n--- Đơn promote Xuất kho → Hoàn thành ---'))
            for o in orders_to_complete:
                self.stdout.write(
                    f'  [{o.code}] {o.customer} | '
                    f'Tổng: {int(o.final_amount):,}đ | Đã thu: {int(o.paid_amount):,}đ'
                )

        all_blocked = orders_pending_approval + orders_blocked_by_approval
        if all_blocked:
            self.stdout.write(self.style.WARNING('\n--- Đơn chờ duyệt (không tự chuyển) ---'))
            for o in all_blocked:
                approver_name = o.approver.get_full_name() if o.approver else '?'
                self.stdout.write(f'  [{o.code}] Chờ duyệt: {approver_name}')

        if not apply:
            self.stdout.write(self.style.NOTICE(
                f'\n⚠️  DRY-RUN: Không thay đổi gì. Thêm --apply để thực thi.'
            ))
            return

        if not orders_to_promote and not orders_to_complete:
            self.stdout.write('\nKhông có đơn nào cần chuyển.')
            return

        with transaction.atomic():
            promoted = 0
            completed = 0
            if orders_to_promote:
                ids = [o.id for o in orders_to_promote]
                promoted = Order.objects.filter(id__in=ids).update(status=1)
            if orders_to_complete:
                ids = [o.id for o in orders_to_complete]
                completed = Order.objects.filter(id__in=ids).update(status=5)

        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Đã promote {promoted} đơn từ Báo giá → Đơn hàng.'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'✅ Đã chuyển {completed} đơn từ Đã xuất kho → Hoàn thành.'
        ))
