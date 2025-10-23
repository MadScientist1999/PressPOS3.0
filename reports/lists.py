from pos.models import Branch
from django.http import (

    JsonResponse,
)

from fiscalization.models import OpenDay
from main.settings import HTML_ROOT


def zreport_list(request):
    branch=Branch.objects.get(id=request.session["branch"])
    return JsonResponse(list(OpenDay.objects.filter(branch=branch).values()),status=200,safe=False)