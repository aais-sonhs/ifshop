import time

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Chạy bộ lập lịch cảnh báo tồn kho, kiểm tra cấu hình mỗi phút.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Chỉ kiểm tra một lần rồi thoát.')
        parser.add_argument('--interval', type=int, default=60, help='Số giây giữa hai lần kiểm tra.')

    def handle(self, *args, **options):
        interval = max(15, int(options.get('interval') or 60))
        while True:
            call_command('send_low_stock_alerts', verbosity=1)
            if options.get('once'):
                return
            time.sleep(interval)
