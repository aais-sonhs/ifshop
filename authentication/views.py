# -*- encoding: utf-8 -*-
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.forms.utils import ErrorList
from django.http import HttpResponse
from .forms import LoginForm, SignUpForm
from django.contrib.sessions.models import Session

def login_view(request):
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
                if user.is_superuser:
                    return redirect("/brand_tbl/")
                return redirect("/report_sales/")
            else:    
                msg = 'Sai tên đăng nhập hoặc mật khẩu'    
        else:
            msg = 'Vui lòng kiểm tra lại thông tin'    

    return render(request, "login.html", {"form": form, "msg" : msg})

def register_user(request):
    msg     = None
    success = 0

    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            form.save()
            username = form.cleaned_data.get("username")
            raw_password = form.cleaned_data.get("password1")
            user = authenticate(username=username, password=raw_password)
            msg     = 'Tạo tài khoản thành công.'
            success = 1
        else:
            msg = 'Thông tin không hợp lệ'    
    else:
        form = SignUpForm()

    return render(request, "register.html", {"form": form, "msg" : msg, "success" : success })

def logout_user(request):
    logout(request)
    return redirect("/login/")