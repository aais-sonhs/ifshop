"""
Helper: get current user's store for data filtering.
Superuser cannot see business data (platform admin only).
Regular user sees only their store's data.
Brand owner sees all stores under their brand.
"""
from functools import wraps
import re
import unicodedata
from django.http import JsonResponse
from django.shortcuts import redirect


def brand_owner_required(view_func):
    """Block superadmin from accessing business pages.
    Superadmin manages platform only — not business data.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_superuser:
            # API calls → 403
            if request.path.startswith('/api/') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Superadmin không có quyền xem dữ liệu kinh doanh'}, status=403)
            # Page views → redirect to brand management
            return redirect('/brand_tbl/')
        return view_func(request, *args, **kwargs)
    return wrapper


def get_user_store(request):
    """Return the Store object for the current user, or None if superuser/no store."""
    if request.user.is_superuser:
        return None
    try:
        return request.user.profile.store
    except Exception:
        return None


def get_user_store_id(request):
    """Return the store ID for the current user, or None if superuser."""
    store = get_user_store(request)
    return store.id if store else None


def filter_by_store(queryset, request, field_name='store'):
    """Filter queryset by user's store(s).
    - Superuser: returns EMPTY (platform admin cannot see business data)
    - Brand owner: sees all stores under their brand(s)
    - Regular user: sees only their store
    """
    if request.user.is_superuser:
        return queryset.none()  # Superadmin không xem dữ liệu kinh doanh
    store_ids = get_managed_store_ids(request.user)
    if store_ids:
        return queryset.filter(**{f'{field_name}_id__in': store_ids})
    # Fallback: user has no store
    return queryset.none()


def is_brand_owner(user):
    """Check if user is a brand owner."""
    from system_management.models import Brand
    return Brand.objects.filter(owner=user, is_active=True).exists()


def get_owned_brands(user):
    """Return brands owned by this user."""
    from system_management.models import Brand
    if user.is_superuser:
        return Brand.objects.filter(is_active=True)
    return Brand.objects.filter(owner=user, is_active=True)


def get_managed_store_ids(user):
    """
    Return store IDs this user can manage:
    - Superadmin: all stores
    - Brand owner: all stores under their brands
    - Regular user: only their own store
    """
    from system_management.models import Store
    if user.is_superuser:
        return list(Store.objects.values_list('id', flat=True))
    # Brand owner
    owned_brands = get_owned_brands(user)
    if owned_brands.exists():
        return list(Store.objects.filter(brand__in=owned_brands).values_list('id', flat=True))
    # Regular user
    try:
        if user.profile.store_id:
            return [user.profile.store_id]
    except Exception:
        pass
    return []


def can_manage_users(user):
    """Check if user can manage other users (superadmin or brand owner)."""
    return user.is_superuser or is_brand_owner(user)


def can_access_module(user, module, action='view'):
    """Check if user has permission to access a module/action.
    Brand owners always have access.
    Regular users need ModulePermission via their role group.
    """
    if user.is_superuser:
        return False  # Superadmin = platform only
    if is_brand_owner(user):
        return True  # Brand owner full access
    # Check via role group
    from system_management.models import ModulePermission
    groups = user.groups.all()
    if not groups.exists():
        return True  # No role group = default allow (legacy users)
    return ModulePermission.objects.filter(
        role_group__group__in=groups,
        module=module, action=action, is_allowed=True
    ).exists()


def report_permission_required(view_func):
    """Block users without report access permission."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not can_access_module(request.user, 'reports', 'view'):
            if request.path.startswith('/api/') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Bạn không có quyền xem báo cáo'}, status=403)
            from django.contrib import messages
            messages.error(request, '⛔ Bạn không có quyền truy cập báo cáo. Liên hệ quản lý để được cấp quyền.')
            return redirect('/')
        return view_func(request, *args, **kwargs)
    return wrapper


def _normalize_role_text(value):
    raw = unicodedata.normalize('NFKD', str(value or ''))
    raw = ''.join(ch for ch in raw if not unicodedata.combining(ch)).lower()
    return re.sub(r'[^a-z0-9]+', ' ', raw).strip()


def can_view_sales_report(user):
    """
    Báo cáo bán hàng chỉ cho tài khoản có vai trò/chức vụ:
    - Giám đốc
    - Kế toán
    """
    if not user or not user.is_authenticated or user.is_superuser:
        return False

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
