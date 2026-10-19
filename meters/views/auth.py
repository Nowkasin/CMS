from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST


def _safe_next_url(request):
    next_url = request.POST.get('next') or request.GET.get('next') or ''
    if url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return reverse('meter_list')


@login_not_required
@sensitive_post_parameters('password')
def login_view(request):
    if request.user.is_authenticated:
        return redirect('meter_list')

    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        login(request, user)
        request.session['cms_person_id'] = getattr(user, 'cms_person_id', '')
        request.session['cms_groups'] = getattr(user, 'cms_groups', [])
        return redirect(_safe_next_url(request))

    return render(
        request,
        'meters/login.html',
        {
            'form': form,
            'next': request.POST.get('next') or request.GET.get('next', ''),
        },
    )


@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')
