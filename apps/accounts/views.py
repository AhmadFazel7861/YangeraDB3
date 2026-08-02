from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from .forms import LoginForm


@require_http_methods(['GET', 'POST'])
def login_view(request):
    """Handle user authentication."""
    if request.user.is_authenticated:
        return redirect('dashboard:index')

    form = LoginForm(request, data=request.POST or None)

    if request.method == 'POST':
        if form.is_valid():
            user = form.get_user()
            # Handle remember me
            if not form.cleaned_data.get('remember_me'):
                request.session.set_expiry(0)
            else:
                request.session.set_expiry(86400 * 30)

            # Log IP
            ip = request.META.get('REMOTE_ADDR')
            user.last_login_ip = ip
            user.save(update_fields=['last_login_ip'])

            login(request, user)

            from apps.activity_logs.services import ActivityLogService
            ActivityLogService.log_login(user, request=request)
            messages.success(request, f'خوش آمدید، {user.display_name}!')

            next_url = request.GET.get('next', 'dashboard:index')
            return redirect(next_url)
        else:
            messages.error(request, 'نام کاربری یا رمز عبور اشتباه است.')

    return render(request, 'accounts/login.html', {'form': form})


@login_required
def logout_view(request):
    """Log out user."""
    username = request.user.display_name

    from apps.activity_logs.services import ActivityLogService
    ActivityLogService.log_logout(request.user, request=request)
    
    logout(request)
    messages.info(request, f'خداحافظ، {username}. با موفقیت خارج شدید.')
    return redirect('accounts:login')


@login_required
def profile_view(request):
    """User profile page — expanded in later phases."""
    return render(request, 'accounts/profile.html', {'user': request.user})