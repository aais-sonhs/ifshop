import json
import logging
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib.auth.models import User
from django.db import models as db_models
from .models import UserProfile, RoleGroup, ServicePrice, PrinterSetting, BusinessConfig, Brand, Store
from core.store_utils import can_manage_users, get_managed_store_ids

logger = logging.getLogger(__name__)


def _get_editable_user(request, user_id):
    """Lấy user mà request.user được phép chỉnh sửa/xóa.

    - Superadmin: truy cập được mọi user.
    - Brand owner: chỉ truy cập user trong store mình quản lý hoặc user chưa gán store.
    """
    if not user_id:
        return None
    queryset = User.objects.all()
    if request.user.is_superuser:
        return queryset.filter(id=user_id).first()

    managed_store_ids = get_managed_store_ids(request.user)
    return queryset.filter(
        db_models.Q(id=user_id),
        db_models.Q(profile__store_id__in=managed_store_ids) |
        db_models.Q(profile__store__isnull=True, is_superuser=False),
    ).distinct().first()


def _get_brand_queryset_for_user(request):
    """Lấy danh sách brand mà user hiện tại được phép xem/chỉnh sửa."""
    if request.user.is_superuser:
        return Brand.objects.all()
    return Brand.objects.filter(owner=request.user)


def _get_brand_for_user(request, brand_id):
    """Lấy brand trong đúng phạm vi user hiện tại được phép thao tác."""
    if not brand_id:
        return None
    return _get_brand_queryset_for_user(request).filter(id=brand_id).first()


def _get_store_queryset_for_user(request):
    """Lấy danh sách store mà user hiện tại được phép quản trị."""
    if request.user.is_superuser:
        return Store.objects.all()
    return Store.objects.filter(id__in=get_managed_store_ids(request.user))


def _get_store_for_user(request, store_id):
    """Lấy store trong đúng phạm vi user hiện tại được phép thao tác."""
    if not store_id:
        return None
    return _get_store_queryset_for_user(request).filter(id=store_id).first()


@login_required(login_url="/login/")
def user_management_tbl(request):
    context = {'active_tab': 'user_management_tbl'}
    return render(request, "system/user_management.html", context)


@login_required(login_url="/login/")
def role_group_tbl(request):
    context = {'active_tab': 'role_group_tbl'}
    return render(request, "system/role_group.html", context)


@login_required(login_url="/login/")
def permission_tbl(request):
    context = {'active_tab': 'permission_tbl'}
    return render(request, "system/permission.html", context)


@login_required(login_url="/login/")
def category_tbl(request):
    context = {'active_tab': 'category_tbl'}
    return render(request, "system/category.html", context)


@login_required(login_url="/login/")
def service_price_tbl(request):
    context = {'active_tab': 'service_price_tbl'}
    return render(request, "system/service_price.html", context)


# ============ API: ROLE GROUP ============

@login_required(login_url="/login/")
def api_get_role_groups(request):
    role_groups = RoleGroup.objects.select_related('group').all()
    data = []
    for rg in role_groups:
        user_count = rg.group.user_set.count() if rg.group else 0
        data.append({
            'id': rg.id, 'name': rg.name,
            'description': rg.description or '',
            'group_id': rg.group_id,
            'is_active': rg.is_active,
            'user_count': user_count,
            'created_at': rg.created_at.strftime('%d/%m/%Y %H:%M') if rg.created_at else '',
        })
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_role_group(request):
    from django.contrib.auth.models import Group
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        rid = data.get('id')
        if rid:
            rg = RoleGroup.objects.get(id=rid)
            rg.name = data.get('name', rg.name)
            rg.description = data.get('description', '')
            rg.is_active = data.get('is_active', True)
            # Update Django Group name to match
            if rg.group:
                rg.group.name = rg.name
                rg.group.save()
            rg.save()
        else:
            name = data.get('name', '')
            if not name:
                return JsonResponse({'status': 'error', 'message': 'Tên nhóm không được để trống'})
            if RoleGroup.objects.filter(name=name).exists():
                return JsonResponse({'status': 'error', 'message': f'Nhóm vai trò "{name}" đã tồn tại'})
            # Create Django Group first
            group = Group.objects.create(name=name)
            rg = RoleGroup.objects.create(
                name=name,
                description=data.get('description', ''),
                group=group,
                is_active=data.get('is_active', True),
            )
        return JsonResponse({'status': 'ok', 'message': 'Lưu nhóm vai trò thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_role_group(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        rg = RoleGroup.objects.get(id=data.get('id'))
        # Delete associated Django Group
        if rg.group:
            rg.group.delete()  # This also deletes the RoleGroup due to CASCADE
        else:
            rg.delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa nhóm vai trò thành công'})
    except RoleGroup.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Không tìm thấy nhóm vai trò'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_assign_role_group(request):
    """Gán/bỏ user vào nhóm vai trò"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        rg = RoleGroup.objects.get(id=data.get('role_group_id'))
        user = User.objects.get(id=data.get('user_id'))
        action = data.get('action', 'add')  # 'add' or 'remove'

        if action == 'add':
            user.groups.add(rg.group)
            msg = f'Đã thêm {user.username} vào nhóm {rg.name}'
        else:
            user.groups.remove(rg.group)
            msg = f'Đã xóa {user.username} khỏi nhóm {rg.name}'
        return JsonResponse({'status': 'ok', 'message': msg})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def business_config_tbl(request):
    from core.store_utils import is_brand_owner
    if not is_brand_owner(request.user):
        from django.contrib import messages
        messages.error(request, 'Chỉ chủ thương hiệu mới được phép cài đặt.')
        return redirect('/dashboard/')
    return render(request, "system/business_config.html", {'active_tab': 'business_config_tbl'})


@login_required(login_url="/login/")
def setting_quotation(request):
    from core.store_utils import is_brand_owner
    if not is_brand_owner(request.user):
        from django.contrib import messages
        messages.error(request, 'Chỉ chủ thương hiệu mới được phép cài đặt.')
        return redirect('/dashboard/')
    return render(request, "system/setting_quotation.html", {'active_tab': 'setting_quotation'})


@login_required(login_url="/login/")
def setting_order(request):
    from core.store_utils import is_brand_owner
    if not is_brand_owner(request.user):
        from django.contrib import messages
        messages.error(request, 'Chỉ chủ thương hiệu mới được phép cài đặt.')
        return redirect('/dashboard/')
    return render(request, "system/setting_order.html", {'active_tab': 'setting_order'})


# ============ API: BUSINESS CONFIG ============

@login_required(login_url="/login/")
def api_get_business_config(request):
    # Load per-brand config
    brand = None
    try:
        profile = request.user.profile
        if profile.store:
            brand = profile.store.brand
    except Exception:
        pass
    if not brand:
        from core.store_utils import is_brand_owner
        if is_brand_owner(request.user):
            brand = Brand.objects.filter(owner=request.user).first()
    c = BusinessConfig.get_config(brand=brand)
    return JsonResponse({
        'data': {
            'business_type': c.business_type,
            'business_type_display': c.get_business_type_display(),
            'business_name': c.business_name,
            'mod_orders': c.mod_orders,
            'mod_quotations': c.mod_quotations,
            'mod_returns': c.mod_returns,
            'mod_packaging': c.mod_packaging,
            'mod_products': c.mod_products,
            'mod_customers': c.mod_customers,
            'mod_finance': c.mod_finance,
            'mod_reports': c.mod_reports,
            'mod_spa': c.mod_spa,
            'mod_pos': c.mod_pos,
            'mod_cafe_tables': c.mod_cafe_tables,
            'opt_quotation_salesperson': c.opt_quotation_salesperson,
            'opt_order_salesperson': c.opt_order_salesperson,
            'opt_order_server_staff': c.opt_order_server_staff,
            'opt_order_approver': c.opt_order_approver,
            'opt_order_bonus': c.opt_order_bonus,
            'opt_loyalty_points': c.opt_loyalty_points,
            'opt_loyalty_rate': c.opt_loyalty_rate,
            'opt_commission': c.opt_commission,
        },
        'business_types': BusinessConfig.BUSINESS_TYPE_CHOICES,
    })


@login_required(login_url="/login/")
def api_save_business_config(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    from core.store_utils import is_brand_owner
    if not is_brand_owner(request.user):
        return JsonResponse({'status': 'error', 'message': 'Chỉ chủ thương hiệu mới được phép thay đổi cài đặt.'}, status=403)
    try:
        data = json.loads(request.body)
        # Load per-brand config
        brand = None
        try:
            profile = request.user.profile
            if profile.store:
                brand = profile.store.brand
        except Exception:
            pass
        if not brand:
            brand = Brand.objects.filter(owner=request.user).first()
        c = BusinessConfig.get_config(brand=brand)
        c.business_type = data.get('business_type', 'custom')
        c.business_name = data.get('business_name', c.business_name)
        c.mod_orders = data.get('mod_orders', True)
        c.mod_quotations = data.get('mod_quotations', True)
        c.mod_returns = data.get('mod_returns', True)
        c.mod_packaging = data.get('mod_packaging', True)
        c.mod_products = data.get('mod_products', True)
        c.mod_customers = data.get('mod_customers', True)
        c.mod_finance = data.get('mod_finance', True)
        c.mod_reports = data.get('mod_reports', True)
        c.mod_spa = data.get('mod_spa', False)
        c.mod_pos = data.get('mod_pos', False)
        c.mod_cafe_tables = data.get('mod_cafe_tables', False)
        c.opt_quotation_salesperson = data.get('opt_quotation_salesperson', False)
        c.opt_order_salesperson = data.get('opt_order_salesperson', False)
        c.opt_order_server_staff = data.get('opt_order_server_staff', False)
        c.opt_order_approver = data.get('opt_order_approver', False)
        c.opt_order_bonus = data.get('opt_order_bonus', False)
        c.opt_loyalty_points = data.get('opt_loyalty_points', False)
        c.opt_loyalty_rate = data.get('opt_loyalty_rate', 10000)
        c.opt_commission = data.get('opt_commission', False)
        c.save()
        return JsonResponse({'status': 'ok', 'message': 'Lưu cấu hình thành công! Reload trang để thấy thay đổi trên menu.'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ API: SERVICE PRICE ============

@login_required(login_url="/login/")
def api_get_service_prices(request):
    items = ServicePrice.objects.all()
    data = [{
        'id': s.id, 'name': s.name, 'price': float(s.price),
        'unit': s.unit or '', 'description': s.description or '',
        'is_active': s.is_active,
    } for s in items]
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_service_price(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        sid = data.get('id')
        if sid:
            s = ServicePrice.objects.get(id=sid)
        else:
            s = ServicePrice()
        s.name = data.get('name', '')
        s.price = data.get('price', 0) or 0
        s.unit = data.get('unit', '')
        s.description = data.get('description', '')
        s.is_active = data.get('is_active', True)
        s.save()
        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_service_price(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        ServicePrice.objects.filter(id=data.get('id')).delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ API: USERS ============

@login_required(login_url="/login/")
def api_get_users(request):
    """Trả về danh sách user theo đúng phạm vi quản trị của tài khoản hiện tại."""
    users = User.objects.all().prefetch_related('groups')

    if request.user.is_superuser:
        # Superadmin chỉ thấy chủ thương hiệu (Brand.owner) + superadmin khác
        brand_owner_ids = list(Brand.objects.filter(owner__isnull=False).values_list('owner_id', flat=True))
        users = users.filter(
            db_models.Q(id__in=brand_owner_ids) |
            db_models.Q(is_superuser=True)
        ).distinct()
    elif can_manage_users(request.user):
        store_ids = get_managed_store_ids(request.user)
        # Include users in managed stores + users without store (just created)
        users = users.filter(
            db_models.Q(profile__store_id__in=store_ids) |
            db_models.Q(profile__store__isnull=True, is_superuser=False)
        ).distinct()
    elif not request.user.is_superuser:
        # Regular user: chỉ thấy chính mình
        users = users.filter(id=request.user.id)

    data = []
    for u in users:
        store_name = ''
        store_id = None
        brand_name = ''
        try:
            if hasattr(u, 'profile') and u.profile.store:
                store_name = u.profile.store.name
                store_id = u.profile.store_id
        except Exception:
            pass
        # Brand mà user sở hữu
        owned_brand = Brand.objects.filter(owner=u).first()
        if owned_brand:
            brand_name = owned_brand.name
        data.append({
            'id': u.id, 'username': u.username,
            'full_name': u.get_full_name() or u.username,
            'first_name': u.first_name or '',
            'last_name': u.last_name or '',
            'email': u.email or '',
            'is_active': u.is_active,
            'is_superuser': u.is_superuser,
            'groups': ', '.join([g.name for g in u.groups.all()]),
            'store_name': store_name,
            'store_id': store_id,
            'brand_name': brand_name,
        })
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_user(request):
    """Tạo/sửa user — brand owner hoặc superadmin"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    if not can_manage_users(request.user):
        return JsonResponse({'status': 'error', 'message': 'Bạn không có quyền quản lý người dùng'})

    try:
        data = json.loads(request.body)
        uid = data.get('id')
        username = data.get('username', '').strip()
        store_id = data.get('store_id')

        # Kiểm tra store gán cho user có thuộc phạm vi mà người thao tác được quản lý hay không.
        if store_id and not request.user.is_superuser:
            allowed_stores = get_managed_store_ids(request.user)
            if int(store_id) not in allowed_stores:
                return JsonResponse({'status': 'error', 'message': 'Cửa hàng không thuộc thương hiệu của bạn'})

        if uid:
            # Khi sửa user, luôn khóa phạm vi theo helper thay vì lấy thẳng theo id.
            user = _get_editable_user(request, uid)
            if not user:
                return JsonResponse({'status': 'error', 'message': 'Bạn không có quyền chỉnh sửa người dùng này'})
            user.first_name = data.get('first_name', '')
            user.last_name = data.get('last_name', '')
            user.email = data.get('email', '')
            user.is_active = data.get('is_active', True)
            # Only superadmin can change password of other superadmins
            password = data.get('password', '')
            if password:
                user.set_password(password)
            user.save()
            # Nếu khóa tài khoản → xóa tất cả session để logout ngay
            if not user.is_active:
                from django.contrib.sessions.models import Session
                from django.utils import timezone
                for session in Session.objects.filter(expire_date__gte=timezone.now()):
                    session_data = session.get_decoded()
                    if str(session_data.get('_auth_user_id')) == str(user.id):
                        session.delete()
        else:
            # Create new
            if not username:
                return JsonResponse({'status': 'error', 'message': 'Tên đăng nhập không được để trống'})
            if User.objects.filter(username=username).exists():
                return JsonResponse({'status': 'error', 'message': f'Tên đăng nhập "{username}" đã tồn tại'})
            password = data.get('password', '')
            if not password:
                return JsonResponse({'status': 'error', 'message': 'Mật khẩu không được để trống'})
            user = User.objects.create_user(
                username=username,
                password=password,
                first_name=data.get('first_name', ''),
                last_name=data.get('last_name', ''),
                email=data.get('email', ''),
                is_active=data.get('is_active', True),
            )

        # Update profile store
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.store_id = store_id or None
        profile.save()

        return JsonResponse({'status': 'ok', 'message': 'Lưu người dùng thành công'})
    except User.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Không tìm thấy người dùng'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_user(request):
    """Xóa user — chỉ brand owner/superadmin"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    if not can_manage_users(request.user):
        return JsonResponse({'status': 'error', 'message': 'Bạn không có quyền'})
    try:
        data = json.loads(request.body)
        user = _get_editable_user(request, data.get('id'))
        if not user:
            return JsonResponse({'status': 'error', 'message': 'Không tìm thấy người dùng'})
        if user.is_superuser:
            return JsonResponse({'status': 'error', 'message': 'Không thể xóa tài khoản Super Admin'})
        if user.id == request.user.id:
            return JsonResponse({'status': 'error', 'message': 'Không thể xóa chính mình'})
        user.delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa người dùng thành công'})
    except User.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Không tìm thấy người dùng'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_get_stores_for_user(request):
    """Lấy danh sách stores mà user hiện tại được quản lý"""
    store_ids = get_managed_store_ids(request.user)
    stores = Store.objects.filter(id__in=store_ids).select_related('brand')
    data = [{
        'id': s.id, 'name': f"{s.brand.name} - {s.name}" if s.brand else s.name,
        'code': s.code,
    } for s in stores]
    return JsonResponse({'data': data})


# ============ API: PRINTER SETTINGS ============

@login_required(login_url="/login/")
def printer_setting_tbl(request):
    context = {'active_tab': 'printer_setting_tbl'}
    return render(request, "system/printer_setting.html", context)


@login_required(login_url="/login/")
def api_get_printers(request):
    printers = PrinterSetting.objects.filter(is_active=True)
    data = [{
        'id': p.id, 'name': p.name,
        'printer_type': p.printer_type,
        'printer_type_display': p.get_printer_type_display(),
        'ip_address': p.ip_address or '',
        'port': p.port,
        'paper_size': p.paper_size,
        'paper_size_display': p.get_paper_size_display(),
        'description': p.description or '',
        'is_default': p.is_default,
        'is_active': p.is_active,
    } for p in printers]
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_printer(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        pid = data.get('id')
        if pid:
            p = PrinterSetting.objects.get(id=pid)
        else:
            p = PrinterSetting()
        p.name = data.get('name', '')
        p.printer_type = data.get('printer_type', 'lan')
        p.ip_address = data.get('ip_address') or None
        p.port = data.get('port', 9100)
        p.paper_size = data.get('paper_size', 'A4')
        p.description = data.get('description', '')
        p.is_default = data.get('is_default', False)
        p.is_active = data.get('is_active', True)

        # Nếu đặt làm mặc định → bỏ mặc định của các máy in khác
        if p.is_default:
            PrinterSetting.objects.exclude(id=p.id if p.id else 0).update(is_default=False)

        p.save()
        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_printer(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        PrinterSetting.objects.filter(id=data.get('id')).delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_test_printer(request):
    """Test kết nối máy in LAN"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        import socket
        data = json.loads(request.body)
        ip = data.get('ip_address', '')
        port = int(data.get('port', 9100))

        if not ip:
            return JsonResponse({'status': 'error', 'message': 'Chưa nhập địa chỉ IP'})

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((ip, port))
        sock.close()

        if result == 0:
            return JsonResponse({'status': 'ok', 'message': f'Kết nối thành công đến {ip}:{port}'})
        else:
            return JsonResponse({'status': 'error', 'message': f'Không thể kết nối đến {ip}:{port}. Kiểm tra lại IP và máy in đã bật chưa.'})
    except socket.timeout:
        return JsonResponse({'status': 'error', 'message': 'Hết thời gian chờ kết nối (timeout)'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_direct_print(request):
    """In trực tiếp qua máy in LAN (gửi raw data qua socket)"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        import socket
        data = json.loads(request.body)
        printer_id = data.get('printer_id')
        html_content = data.get('html_content', '')

        if not printer_id:
            return JsonResponse({'status': 'error', 'message': 'Chưa chọn máy in'})

        printer = PrinterSetting.objects.get(id=printer_id)

        if not printer.ip_address:
            return JsonResponse({'status': 'error', 'message': 'Máy in chưa có địa chỉ IP'})

        # Thử kết nối test trước
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        result = sock.connect_ex((printer.ip_address, printer.port))

        if result != 0:
            sock.close()
            return JsonResponse({'status': 'error', 'message': f'Không kết nối được máy in {printer.name} ({printer.ip_address}:{printer.port})'})

        # Tạo lệnh in cơ bản (text mode)
        # Với máy in LAN hỗ trợ PCL/PostScript, cần convert HTML → PDF → gửi
        # Ở đây gửi raw text đơn giản
        try:
            # Thử import pdfkit/weasyprint để convert HTML → PDF
            import subprocess
            import tempfile
            import os

            # Tạo file HTML tạm
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
                f.write(f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>body{{font-family:Arial,sans-serif;font-size:12px;margin:10mm 15mm;}}
table{{width:100%;border-collapse:collapse;}} th,td{{border:1px solid #999;padding:5px 8px;}}
th{{background:#f0f0f0;font-weight:bold;text-align:center;}}
.text-right{{text-align:right;}} .text-center{{text-align:center;}}
</style></head><body>{html_content}</body></html>""")
                html_path = f.name

            # Convert HTML to PDF bằng wkhtmltopdf (thường có sẵn trên Linux)
            pdf_path = html_path.replace('.html', '.pdf')
            paper_map = {'A4': 'A4', 'A5': 'A5', '80mm': 'Custom.80x297', '58mm': 'Custom.58x297', 'letter': 'Letter'}
            paper = paper_map.get(printer.paper_size, 'A4')

            wk_result = subprocess.run(
                ['wkhtmltopdf', '--page-size', paper, '--quiet', html_path, pdf_path],
                capture_output=True, timeout=30
            )

            if wk_result.returncode == 0 and os.path.exists(pdf_path):
                with open(pdf_path, 'rb') as pdf_file:
                    pdf_data = pdf_file.read()
                sock.sendall(pdf_data)
                sock.close()
                os.unlink(html_path)
                os.unlink(pdf_path)
                return JsonResponse({'status': 'ok', 'message': f'Đã gửi lệnh in đến {printer.name}'})
            else:
                sock.close()
                os.unlink(html_path)
                # Fallback: gửi text
                return JsonResponse({'status': 'error', 'message': 'Không thể tạo PDF. Hãy cài wkhtmltopdf: sudo apt install wkhtmltopdf'})

        except FileNotFoundError:
            sock.close()
            return JsonResponse({'status': 'error', 'message': 'Chưa cài wkhtmltopdf. Chạy: sudo apt install wkhtmltopdf'})

    except PrinterSetting.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Không tìm thấy máy in'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ BRAND & STORE ============

@login_required(login_url="/login/")
def brand_tbl(request):
    return render(request, "system/brand_list.html", {'active_tab': 'brand_tbl'})


@login_required(login_url="/login/")
def api_get_brands(request):
    """Trả về danh sách brand/store mà user hiện tại được phép quản trị."""
    brands = _get_brand_queryset_for_user(request).prefetch_related('stores', 'stores__staff_profiles__user')
    data = []
    for b in brands:
        stores = []
        for s in b.stores.all():
            # Lấy danh sách tài khoản thuộc store
            store_users = []
            for p in s.staff_profiles.select_related('user').all():
                u = p.user
                store_users.append({
                    'username': u.username,
                    'full_name': u.get_full_name() or u.username,
                    'is_staff': u.is_staff,
                    'is_superuser': u.is_superuser,
                })
            stores.append({
                'id': s.id, 'code': s.code, 'name': s.name,
                'phone': s.phone or '', 'email': s.email or '',
                'address': s.address or '', 'city': s.city or '', 'district': s.district or '',
                'manager_id': s.manager_id, 'manager_name': s.manager.get_full_name() if s.manager else '',
                'open_time': s.open_time.strftime('%H:%M') if s.open_time else '',
                'close_time': s.close_time.strftime('%H:%M') if s.close_time else '',
                'is_active': s.is_active,
                'users': store_users,
            })
        data.append({
            'id': b.id, 'name': b.name,
            'business_type': b.business_type,
            'business_type_display': b.get_business_type_display(),
            'logo': b.logo.url if b.logo else '',
            'description': b.description or '',
            'phone': b.phone or '', 'email': b.email or '',
            'website': b.website or '', 'address': b.address or '',
            'tax_code': b.tax_code or '',
            'owner_id': b.owner_id,
            'owner_name': b.owner.get_full_name() if b.owner else '',
            'owner_username': b.owner.username if b.owner else '',
            'is_active': b.is_active,
            'stores': stores,
            'store_count': len(stores),
        })
    users = [{'id': u.id, 'name': u.get_full_name() or u.username} for u in User.objects.filter(is_active=True)]
    return JsonResponse({'data': data, 'users': users})


@login_required(login_url="/login/")
def api_save_brand(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        bid = data.get('id')
        if bid:
            b = _get_brand_for_user(request, bid)
            if not b:
                return JsonResponse({'status': 'error', 'message': 'Không tìm thấy thương hiệu'})
        else:
            b = Brand()
        b.name = data.get('name', '')
        b.business_type = data.get('business_type', 'retail')
        b.description = data.get('description', '')
        b.phone = data.get('phone', '')
        b.email = data.get('email', '')
        b.website = data.get('website', '')
        b.address = data.get('address', '')
        b.tax_code = data.get('tax_code', '')
        # Brand owner chỉ được quản lý thương hiệu của chính mình; superadmin mới được gán owner tùy ý.
        b.owner_id = (data.get('owner_id') or None) if request.user.is_superuser else request.user.id
        b.is_active = data.get('is_active', True)
        b.save()
        return JsonResponse({'status': 'ok', 'message': 'Lưu thương hiệu thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_brand(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        brand = _get_brand_for_user(request, data.get('id'))
        if not brand:
            return JsonResponse({'status': 'error', 'message': 'Không tìm thấy thương hiệu'})
        brand.delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa thương hiệu thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_save_store(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        sid = data.get('id')
        if sid:
            s = _get_store_for_user(request, sid)
            if not s:
                return JsonResponse({'status': 'error', 'message': 'Không tìm thấy cửa hàng'})
        else:
            s = Store()

        brand_id = data.get('brand_id')
        brand = _get_brand_for_user(request, brand_id)
        if not brand:
            return JsonResponse({'status': 'error', 'message': 'Thương hiệu không thuộc phạm vi quản lý của bạn'})

        # Luôn kiểm tra brand trước khi gán store để brand owner không sửa chéo brand.
        s.brand = brand
        s.code = data.get('code', '')
        s.name = data.get('name', '')
        s.phone = data.get('phone', '')
        s.email = data.get('email', '')
        s.address = data.get('address', '')
        s.city = data.get('city', '')
        s.district = data.get('district', '')
        s.manager_id = data.get('manager_id') or None
        s.open_time = data.get('open_time') or None
        s.close_time = data.get('close_time') or None
        s.is_active = data.get('is_active', True)
        s.save()
        return JsonResponse({'status': 'ok', 'message': 'Lưu cửa hàng thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_store(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        store = _get_store_for_user(request, data.get('id'))
        if not store:
            return JsonResponse({'status': 'error', 'message': 'Không tìm thấy cửa hàng'})
        store.delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa cửa hàng thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ PROFILE APIs ============

@login_required(login_url="/login/")
def api_get_my_profile(request):
    """Lấy thông tin profile của user hiện tại"""
    u = request.user
    profile, _ = UserProfile.objects.get_or_create(user=u)
    return JsonResponse({
        'status': 'ok',
        'data': {
            'id': u.id,
            'username': u.username,
            'first_name': u.first_name,
            'last_name': u.last_name,
            'full_name': u.get_full_name() or u.username,
            'email': u.email,
            'phone': profile.phone or '',
            'avatar_url': profile.avatar.url if profile.avatar else '',
            'store': profile.store.name if profile.store else '',
            'brand': profile.store.brand.name if profile.store else '',
            'is_staff': u.is_staff,
            'is_superuser': u.is_superuser,
        }
    })


@login_required(login_url="/login/")
def api_change_my_password(request):
    """Đổi mật khẩu — tất cả user đều có quyền đổi pass của mình"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        old_pw = data.get('old_password', '')
        new_pw = data.get('new_password', '')
        confirm_pw = data.get('confirm_password', '')

        if not old_pw or not new_pw:
            return JsonResponse({'status': 'error', 'message': 'Vui lòng nhập đủ thông tin'})
        if new_pw != confirm_pw:
            return JsonResponse({'status': 'error', 'message': 'Mật khẩu xác nhận không khớp'})
        if len(new_pw) < 6:
            return JsonResponse({'status': 'error', 'message': 'Mật khẩu mới tối thiểu 6 ký tự'})
        if not request.user.check_password(old_pw):
            return JsonResponse({'status': 'error', 'message': 'Mật khẩu cũ không đúng'})

        request.user.set_password(new_pw)
        request.user.save()
        from django.contrib.auth import update_session_auth_hash
        update_session_auth_hash(request, request.user)
        return JsonResponse({'status': 'ok', 'message': 'Đổi mật khẩu thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_upload_my_avatar(request):
    """Upload ảnh đại diện profile — convert sang JPG"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        import os
        from PIL import Image
        from io import BytesIO
        from django.core.files.base import ContentFile

        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        if 'avatar' in request.FILES:
            if profile.avatar:
                try:
                    if os.path.isfile(profile.avatar.path):
                        os.remove(profile.avatar.path)
                except Exception:
                    pass
            uploaded = request.FILES['avatar']
            img = Image.open(uploaded)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            buffer = BytesIO()
            img.save(buffer, format='JPEG', quality=90)
            buffer.seek(0)
            filename = f"user_{request.user.username}.jpg"
            profile.avatar.save(filename, ContentFile(buffer.read()), save=True)
            return JsonResponse({'status': 'ok', 'message': 'Cập nhật ảnh thành công', 'avatar_url': profile.avatar.url})
        return JsonResponse({'status': 'error', 'message': 'Không có file ảnh'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})
