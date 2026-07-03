"""Helper lọc dữ liệu theo store/brand của user hiện tại.

Quy ước quyền:
- Superuser chỉ quản trị nền tảng, không xem dữ liệu kinh doanh.
- User thường chỉ xem dữ liệu của store đang được gán.
- Brand owner xem dữ liệu của toàn bộ store thuộc brand mình sở hữu.
"""
from functools import wraps
import re
import unicodedata
from django.http import JsonResponse
from django.shortcuts import redirect


def brand_owner_required(view_func):
    """Chặn superadmin vào các trang nghiệp vụ kinh doanh.

    Superadmin chỉ quản trị nền tảng nên không được đọc dữ liệu vận hành của shop.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_superuser:
            # Với API, trả lỗi rõ ràng để frontend xử lý thay vì redirect HTML.
            if request.path.startswith('/api/') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Superadmin không có quyền xem dữ liệu kinh doanh'}, status=403)
            # Với trang HTML, đưa superadmin về khu vực quản trị brand.
            return redirect('/brand-tbl/')
        return view_func(request, *args, **kwargs)
    return wrapper


def get_user_store(request):
    """Trả về store của user hiện tại; None nếu là superuser hoặc chưa gán store."""
    if request.user.is_superuser:
        return None
    try:
        return request.user.profile.store
    except Exception:
        return None


def get_user_store_id(request):
    """Trả về store_id của user hiện tại để dùng ở các filter đơn giản."""
    store = get_user_store(request)
    return store.id if store else None


def filter_by_store(queryset, request, field_name='store'):
    """Lọc queryset theo store mà user được quyền quản lý.

    - Superuser: trả queryset rỗng vì không được xem dữ liệu kinh doanh.
    - Brand owner: xem được toàn bộ store dưới brand của mình.
    - User thường: chỉ xem store được gán trên profile.
    """
    if request.user.is_superuser:
        return queryset.none()  # Superadmin không xem dữ liệu kinh doanh
    store_ids = get_managed_store_ids(request.user)
    if store_ids:
        return queryset.filter(**{f'{field_name}_id__in': store_ids})
    # User không gắn store/brand thì không có phạm vi dữ liệu hợp lệ.
    return queryset.none()


def is_brand_owner(user):
    """Kiểm tra user có đang sở hữu brand đang hoạt động hay không."""
    from system_management.models import Brand
    return Brand.objects.filter(
        owner=user,
        is_active=True,
        brand_type=Brand.TYPE_COMPANY,
    ).exists()


def get_owned_brands(user):
    """Trả danh sách công ty user được quyền quản trị."""
    from system_management.models import Brand
    if user.is_superuser:
        return Brand.objects.filter(is_active=True, brand_type=Brand.TYPE_COMPANY)
    return Brand.objects.filter(owner=user, is_active=True, brand_type=Brand.TYPE_COMPANY)


def get_company_brand_for_user(user, store=None):
    """Trả về công ty gốc trong ngữ cảnh hiện tại."""
    from system_management.models import Brand

    if store and getattr(store, 'brand_id', None):
        brand = store.brand
        if getattr(brand, 'brand_type', Brand.TYPE_COMPANY) == Brand.TYPE_COMPANY:
            return brand

    owned_brands = get_owned_brands(user)
    return owned_brands.order_by('name').first()


def get_related_brands_for_user(user, store=None):
    """Trả danh sách nhãn hiệu in user có thể dùng trong ngữ cảnh hiện tại.

    - Luôn ưu tiên công ty của store hiện tại làm brand mặc định để in.
    - Các nhãn hiệu phụ chỉ là thông tin hiển thị trên chứng từ.
    """
    from system_management.models import Brand

    company_brand = get_company_brand_for_user(user, store=store)
    if not company_brand:
        try:
            profile_store = user.profile.store
            company_brand = get_company_brand_for_user(user, store=profile_store)
        except Exception:
            company_brand = None

    if not company_brand:
        return Brand.objects.none()

    allowed_ids = []
    if getattr(company_brand, 'is_active', False):
        allowed_ids.append(company_brand.id)

    if getattr(company_brand, 'owner_id', None):
        allowed_ids.extend(
            Brand.objects.filter(
                owner_id=company_brand.owner_id,
                is_active=True,
                brand_type=Brand.TYPE_PRINT_LABEL,
            ).values_list('id', flat=True)
        )
    return Brand.objects.filter(id__in=allowed_ids).order_by('brand_type', 'name')


def get_managed_store_ids(user):
    """Trả danh sách store_id user có thể quản lý.

    - Superadmin: toàn bộ store để phục vụ màn hình quản trị cấu hình.
    - Brand owner: toàn bộ store thuộc các brand đang sở hữu.
    - User thường: chỉ store gắn trên profile.
    """
    from system_management.models import Store
    if user.is_superuser:
        return list(Store.objects.values_list('id', flat=True))
    # Brand owner quản lý nhiều store thông qua quan hệ Brand -> Store.
    owned_brands = get_owned_brands(user)
    if owned_brands.exists():
        return list(Store.objects.filter(brand__in=owned_brands).values_list('id', flat=True))
    # User thường lấy phạm vi từ profile.store_id.
    try:
        if user.profile.store_id:
            return [user.profile.store_id]
    except Exception:
        pass
    return []


def can_manage_users(user):
    """Kiểm tra quyền quản lý người dùng: chỉ superadmin hoặc brand owner."""
    return user.is_superuser or is_brand_owner(user)


def can_access_module(user, module, action='view'):
    """Kiểm tra user có quyền truy cập module/action hay không.

    Brand owner có toàn quyền trong phạm vi brand; user thường kiểm tra qua
    ModulePermission gắn với role group.
    """
    if user.is_superuser:
        return False  # Superadmin chỉ quản trị nền tảng.
    if is_brand_owner(user):
        return True  # Brand owner có toàn quyền nghiệp vụ trong brand.
    # Kiểm tra quyền chi tiết qua các group đang gán cho user.
    from system_management.models import ModulePermission
    groups = user.groups.all()
    if not groups.exists():
        return True  # User legacy chưa gán role group vẫn được phép như trước.
    return ModulePermission.objects.filter(
        role_group__group__in=groups,
        module=module, action=action, is_allowed=True
    ).exists()


def report_permission_required(view_func):
    """Chặn user không có quyền xem module báo cáo."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not can_access_module(request.user, 'reports', 'view'):
            if request.path.startswith('/api/') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Bạn không có quyền xem báo cáo'}, status=403)
            from django.contrib import messages
            messages.error(request, '⛔ Bạn không có quyền truy cập báo cáo. Liên hệ quản lý để được cấp quyền.')
            return redirect('/dashboard/')
        return view_func(request, *args, **kwargs)
    return wrapper


def _normalize_role_text(value):
    raw = unicodedata.normalize('NFKD', str(value or ''))
    raw = raw.replace('đ', 'd').replace('Đ', 'D')
    raw = ''.join(ch for ch in raw if not unicodedata.combining(ch)).lower()
    return re.sub(r'[^a-z0-9]+', ' ', raw).strip()


def can_view_sales_report(user):
    """
    Báo cáo bán hàng dành cho chủ thương hiệu hoặc tài khoản Giám đốc / Kế toán.
    """
    if not user or not user.is_authenticated or user.is_superuser:
        return False

    if is_brand_owner(user):
        return True

    labels = list(user.groups.values_list('name', flat=True))
    try:
        if user.profile.position:
            labels.append(user.profile.position)
    except Exception:
        pass

    keywords = (
        'giam doc',
        'giamdoc',
        'ke toan',
        'ketoan',
        'director',
        'accountant',
    )

    for label in labels:
        normalized = _normalize_role_text(label)
        compact = normalized.replace(' ', '')
        if any(keyword in normalized or keyword.replace(' ', '') in compact for keyword in keywords):
            return True
    return False
