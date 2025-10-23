# myapp/middleware/license_middleware.py
from django.http import JsonResponse,HttpResponseNotAllowed
from .settings import LICENSE_VALID, LICENSE_MESSAGE 
from django.http import HttpResponseForbidden
from django.contrib.auth import get_user

class LicenseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not LICENSE_VALID:
            # Return JSON to API consumers
            return JsonResponse({
                "error": "License expired",
                "message": LICENSE_MESSAGE
            }, status=503)
        return self.get_response(request)


class PermissionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from .permission import PERMISSION_MAP as permission_map

        try:
            user = get_user(request)
            
            for key, perm in permission_map.items():
                if request.path.startswith(key):
                    required_permission = perm
                    break
            not_permitted = (
                required_permission is not None
                and required_permission not in user.get_group_permissions()
            )
            not_permitted=False
            print("Is permitted:", not not_permitted)

        except Exception as e:
            print("Middleware error:", str(e))
            not_permitted = False

        if not_permitted:
            return HttpResponseForbidden("Permission denied")
        return self.get_response(request)
