from django.shortcuts import redirect, render


def page_not_found(request, exception=None):
    """ใช้หน้าเดียวกับการปฏิเสธสิทธิ์เพื่อไม่เปิดเผยว่า URL มีอยู่จริง"""
    if not request.user.is_authenticated:
        return redirect('login')
    if not request.session.get('cms_permissions', {}):
        return redirect('no_permission')
    return render(request, 'meters/404.html', status=404)

