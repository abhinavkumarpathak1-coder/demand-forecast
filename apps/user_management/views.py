from django.utils.translation import gettext as _
from django.shortcuts import render, redirect
from django.contrib.auth import logout, authenticate, login
from django.contrib import messages

# Create your views here.

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        next_url = request.POST.get('next', '')

        if not username or not password:
            messages.error(request, _('请填写用户名和密码'))
            return render(request, 'user_management/login.html', {'next': next_url})

        user = authenticate(request, username=username, password=password)
        if user is not None:
            if user.is_active:
                login(request, user)
                if next_url:
                    return redirect(next_url)
                return redirect('home')
            else:
                messages.error(request, _('该账户已被禁用'))
        else:
            messages.error(request, _('用户名或密码错误'))

        return render(request, 'user_management/login.html', {'next': next_url})

    # GET
    next_url = request.GET.get('next', '')
    return render(request, 'user_management/login.html', {'next': next_url})


def register(request):
    return render(request, 'user_management/register.html')


def dashboard(request):
    return render(request, 'user_management/dashboard.html')


def logout_view(request):
    logout(request)
    return redirect('user_management:login')


def permissions(request):
    return render(request, 'user_management/permissions.html')
