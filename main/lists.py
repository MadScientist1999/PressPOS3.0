from pos.models import Branch
from django.http import JsonResponse,HttpResponse
from django.views.decorators.csrf import csrf_exempt
from .models import User,Shift
from django.core.cache import cache


@csrf_exempt
def branch_list(request):
    
    branches=list(Branch.objects.all().values())
    return JsonResponse(branches,safe=False)

@csrf_exempt
def user_list(request):
    users=list(User.objects.all().values("id","username","first_name","last_name","email"))
    return JsonResponse(users,safe=False)

def user_shift_list(request,user_id):
    if request.method != "GET":
        return HttpResponse(status=500)

    cache_key = f"user_shift_list"
    data = cache.get(cache_key)
    print("Fetching receipt list from cache:")
    if data is None:
        shifts = Shift.objects.filter(user=user_id).order_by("id")
        data = list(shifts.values())
        cache.set(cache_key, data, timeout=60*60)  # cache 1 hour
        print("Cache miss - queried DB and set cache.")
    return JsonResponse(data, safe=False, status=200)