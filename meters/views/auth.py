from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import redirect, render
from django.urls import Resolver404, resolve, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from ..permissions import URL_PERMISSION_MAP, first_allowed_url_name


def _permission_home_url(permissions):
    url_name = first_allowed_url_name(permissions)
    return reverse(url_name or 'no_permission')


def _safe_next_url(request):
    permissions = request.session.get('cms_permissions', {})
    if not permissions:
        return reverse('no_permission')

    next_url = request.POST.get('next') or request.GET.get('next') or ''
    is_safe_url = url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    )
    if is_safe_url and next_url not in {'', '/'}:
        try:
            url_name = resolve(next_url).url_name
        except Resolver404:
            url_name = None
        required_permission = URL_PERMISSION_MAP.get(url_name)
        if required_permission and permissions.get(required_permission):
            return next_url
    return _permission_home_url(permissions)


@login_not_required
@sensitive_post_parameters('password')
def login_view(request):
    if request.user.is_authenticated:
        return redirect(
            _permission_home_url(
                request.session.get('cms_permissions', {})
            )
        )

    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        login(request, user)
        request.session['cms_person_id'] = getattr(user, 'cms_person_id', '')
        request.session['cms_display_name'] = getattr(
            user,
            'cms_display_name',
            user.username,
        )
        request.session['cms_groups'] = getattr(user, 'cms_groups', [])
        request.session['cms_has_access'] = getattr(
            user,
            'cms_has_access',
            False,
        )
        request.session['cms_menus'] = getattr(user, 'cms_menus', [])
        request.session['cms_menu_ids'] = getattr(user, 'cms_menu_ids', [])
        request.session['cms_permissions'] = getattr(
            user,
            'cms_permissions',
            {},
        )
        request.session['cms_home_url'] = _permission_home_url(
            request.session['cms_permissions']
        )
        return redirect(_safe_next_url(request))

    return render(
        request,
        'meters/login.html',
        {
            'form': form,
            'next': request.POST.get('next') or request.GET.get('next', ''),
        },
    )


def no_permission_view(request):
    permissions = request.session.get('cms_permissions', {})
    if permissions:
        return redirect(_permission_home_url(permissions))

    return render(
        request,
        'meters/no_permission.html',
        status=403,
    )


@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')
