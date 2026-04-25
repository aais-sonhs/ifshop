"""
Middleware: Block superadmin from accessing business pages/APIs.
Superadmin only manages brands, stores, accounts — NOT business data.
"""
from django.http import JsonResponse
from django.shortcuts import redirect


class SuperadminAccessMiddleware:
    """Block superadmin from accessing business routes.
    Allowed paths for superadmin (platform management only):
    - /brand-tbl/, /api/brands/*, /api/stores/*
    - /user-management-tbl/, /api/users/*
    - /category-tbl/, /service-price-tbl/, /api/service-prices/*
    - /printer-setting-tbl/, /api/printers/*
    - /business-config/, /api/business-config/*
    - /role-group-tbl/, /permission-tbl/, /api/role-groups/*
    - /login/, /logout/, /register/, /admin/
    - /api/profile/*, /api/stores-for-user/
    - Static/media files
    """

    ALLOWED_PREFIXES = (
        '/login/', '/logout/', '/register/', '/admin/',
        '/brand-tbl/', '/api/brands/', '/api/stores/',
        '/user-management-tbl/', '/api/users/', '/api/stores-for-user/',
        '/category-tbl/', '/service-price-tbl/', '/api/service-prices/',
        '/printer-setting-tbl/', '/api/printers/',
        '/business-config/', '/api/business-config/',
        '/role-group-tbl/', '/permission-tbl/', '/api/role-groups/',
        '/api/profile/',
        '/static/', '/media/', '/favicon',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            hasattr(request, 'user')
            and request.user.is_authenticated
            and request.user.is_superuser
        ):
            path = request.path
            # Check if path is allowed
            if not any(path.startswith(prefix) for prefix in self.ALLOWED_PREFIXES):
                # API calls → 403
                if path.startswith('/api/') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse(
                        {'error': 'Superadmin không có quyền truy cập dữ liệu kinh doanh'},
                        status=403
                    )
                # Page views → redirect to brand management
                return redirect('/brand-tbl/')

        return self.get_response(request)
