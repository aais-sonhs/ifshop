import json
import logging

from django.contrib.auth import logout
from django.shortcuts import redirect

logger = logging.getLogger(__name__)


class ActiveUserMiddleware:
    """
    Middleware kiểm tra user có bị khóa không.
    Nếu user đang login nhưng is_active=False → tự logout ngay.
    Áp dụng mọi request → user bị khóa sẽ bị đá ra khỏi hệ thống
    trên TẤT CẢ máy/trình duyệt trong vòng 1 request tiếp theo.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not request.user.is_active:
            logout(request)
            return redirect('/login/')
        return self.get_response(request)


class SystemDeleteLogMiddleware:
    """Ghi nhận mọi thao tác xóa thành công từ các bảng nghiệp vụ.

    Các màn hình đều gọi API POST có hậu tố ``/delete/``. Ghi ở middleware
    giúp không bỏ sót bảng mới và chỉ tạo log sau khi endpoint trả về thành
    công, không làm thay đổi logic xóa hiện tại.
    """

    MODULE_LABELS = {
        'products': 'Sản phẩm / kho',
        'warehouses': 'Kho hàng',
        'suppliers': 'Nhà cung cấp',
        'goods-receipts': 'Phiếu nhập',
        'purchase-returns': 'Trả hàng nhập',
        'stock-transfers': 'Chuyển kho',
        'stock-checks': 'Kiểm hàng',
        'purchase-orders': 'Đơn nhập hàng',
        'locations': 'Vị trí sản phẩm',
        'customers': 'Khách hàng',
        'customer-groups': 'Nhóm khách hàng',
        'cafe-tables': 'Bàn phục vụ',
        'orders': 'Đơn hàng',
        'quotations': 'Báo giá',
        'packagings': 'Đóng gói',
        'receipts': 'Phiếu thu',
        'payments': 'Phiếu chi',
        'payment-methods': 'Phương thức thanh toán',
        'service-prices': 'Giá dịch vụ',
        'users': 'Người dùng',
        'role-groups': 'Nhóm vai trò',
        'print-brands': 'Nhãn in',
        'printers': 'Máy in',
        'brands': 'Thương hiệu',
        'stores': 'Cửa hàng',
        'spa': 'Spa',
    }

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _payload(request):
        try:
            if request.body:
                payload = json.loads(request.body.decode('utf-8'))
                if isinstance(payload, dict):
                    return payload
        except (TypeError, ValueError, UnicodeDecodeError):
            pass
        except Exception:
            pass
        try:
            return request.POST.dict()
        except Exception:
            return {}

    @staticmethod
    def _object_id(payload):
        object_id = payload.get('id') or payload.get('object_id')
        if object_id:
            return str(object_id)
        for key, value in payload.items():
            if key.endswith('_id') and value not in (None, ''):
                return str(value)
        return ''

    def _write_log(self, request, response):
        if request.method != 'POST' or '/delete/' not in request.path:
            return
        if not getattr(request.user, 'is_authenticated', False):
            return
        if response.status_code >= 400:
            return
        try:
            result = json.loads(response.content.decode('utf-8'))
        except (TypeError, ValueError, UnicodeDecodeError):
            return
        if not isinstance(result, dict) or result.get('status') != 'ok':
            return

        payload = self._payload(request)
        path_parts = [part for part in request.path.strip('/').split('/') if part]
        resource = path_parts[1] if len(path_parts) > 1 and path_parts[0] == 'api' else (path_parts[0] if path_parts else 'system')
        module = self.MODULE_LABELS.get(resource, resource.replace('-', ' ').title())[:50]
        endpoint = getattr(getattr(request, 'resolver_match', None), 'url_name', None) or request.path
        object_id = self._object_id(payload)
        message = result.get('message') or 'Xóa thành công'
        description = f'{message} · API: {endpoint}'
        if object_id:
            description += f' · ID: {object_id}'
        forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
        ip_address = (forwarded_for.split(',')[0].strip() if forwarded_for else request.META.get('REMOTE_ADDR')) or None

        # Import lazily so middleware loading does not depend on app registry order.
        from .models import SystemLog

        SystemLog.objects.create(
            user=request.user,
            action='delete',
            module=module,
            description=description,
            object_id=object_id or None,
            old_data={'path': request.path, 'payload': payload},
            ip_address=ip_address,
        )

    def __call__(self, request):
        response = self.get_response(request)
        try:
            self._write_log(request, response)
        except Exception:
            # Logging must never turn a successful delete into a failed request.
            logger.exception('Unable to write system delete log for %s', request.path)
        return response
