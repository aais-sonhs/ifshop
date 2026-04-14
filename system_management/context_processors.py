from .models import BusinessConfig
from core.store_utils import is_brand_owner, can_view_sales_report


def business_config(request):
    """Inject business config (per-brand), user's store, and brand owner flag into all templates"""
    try:
        brand = None
        ctx = {}

        if hasattr(request, 'user') and request.user.is_authenticated:
            try:
                profile = request.user.profile
                ctx['user_store'] = profile.store
                ctx['user_store_id'] = profile.store_id
                if profile.store:
                    brand = profile.store.brand
            except Exception:
                ctx['user_store'] = None
                ctx['user_store_id'] = None

            # Check brand owner — if user owns a brand, use that brand
            ctx['is_brand_owner'] = is_brand_owner(request.user)
            ctx['can_view_sales_report'] = can_view_sales_report(request.user)
            if not brand and ctx['is_brand_owner']:
                from .models import Brand
                brand = Brand.objects.filter(owner=request.user).first()

            # Load config per-brand (fallback to default if no brand config)
            config = BusinessConfig.get_config(brand=brand)
            ctx['biz'] = config
            ctx['user_brand'] = brand

            # Warehouse count for menu visibility
            from core.store_utils import get_managed_store_ids
            from products.models import Warehouse
            managed_ids = get_managed_store_ids(request.user)
            ctx['warehouse_count'] = Warehouse.objects.filter(
                store_id__in=managed_ids, is_active=True
            ).count() if managed_ids else 0

            # Pending approval count for menu badge
            try:
                from orders.models import Order
                if ctx['is_brand_owner']:
                    ctx['pending_approval_count'] = Order.objects.filter(
                        approval_status=1, store_id__in=managed_ids
                    ).count() if managed_ids else 0
                else:
                    ctx['pending_approval_count'] = Order.objects.filter(
                        approver=request.user, approval_status=1
                    ).count()
            except Exception:
                ctx['pending_approval_count'] = 0
        else:
            config = BusinessConfig.get_config()
            ctx['biz'] = config
            ctx['user_store'] = None
            ctx['user_store_id'] = None
            ctx['is_brand_owner'] = False
            ctx['can_view_sales_report'] = False
            ctx['warehouse_count'] = 0
            ctx['user_brand'] = None

        return ctx
    except Exception:
        return {'biz': None, 'user_store': None, 'user_store_id': None, 'is_brand_owner': False, 'can_view_sales_report': False}
