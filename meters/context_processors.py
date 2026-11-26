from .access_control import is_cms_admin


def cms_ui(request):
    return {'cms_is_admin': is_cms_admin(request)}
