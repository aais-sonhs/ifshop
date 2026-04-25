# -*- encoding: utf-8 -*-
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.utils.http import url_has_allowed_host_and_scheme
from .forms import LoginForm
from core.store_utils import can_view_sales_report


def _get_post_login_redirect(request, user):
    """Chọn URL chuyển hướng sau đăng nhập theo next-url hợp lệ và vai trò user."""
    next_url = (request.POST.get('next') or request.GET.get('next') or '').strip()
    if next_url and next_url not in ('/', '/login/'):
        if url_has_allowed_host_and_scheme(
            url=next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return next_url

    if user.is_superuser:
        return "/brand-tbl/"
    if can_view_sales_report(user):
        return "/report-sales/"
    return "/dashboard/"


def login_view(request):
    """Xử lý trang đăng nhập và điều hướng user về đúng khu vực được phép xem."""
    if request.user.is_authenticated:
        return redirect(_get_post_login_redirect(request, request.user))

    if not request.session.session_key:
        request.session.save()
    else:
        session_id = request.session.session_key
        if (session_id is not None) and len(str(session_id)) > 0:
            request.session.pop(session_id, None)

    form = LoginForm(request.POST or None)
    msg = None
    if request.method == "POST":
        if form.is_valid():
            username = form.cleaned_data.get("username")
            password = form.cleaned_data.get("password")
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect(_get_post_login_redirect(request, user))
            else:
                msg = 'Sai tên đăng nhập hoặc mật khẩu'
        else:
            msg = 'Vui lòng kiểm tra lại thông tin'

    return render(request, "login.html", {"form": form, "msg": msg})


def register_user(request):
    """Không cho tự đăng ký public; tài khoản phải tạo qua màn quản lý user."""
    return redirect("/login/")


def logout_user(request):
    """Đăng xuất user hiện tại và quay về màn hình đăng nhập."""
    logout(request)
    return redirect("/login/")
