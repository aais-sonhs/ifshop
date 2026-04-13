from django.contrib.auth import logout
from django.shortcuts import redirect


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
