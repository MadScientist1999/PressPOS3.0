from django.http import JsonResponse,HttpResponse
from django.views.decorators.csrf import csrf_exempt
from .models import OpenDay,FiscalBranch
import datetime

@csrf_exempt
def time_to_close(request):
  try: 
   branch=FiscalBranch.objects.get(id=request.session["branch"])
   time=datetime.datetime.fromisoformat(OpenDay.objects.filter(open=1,branch=branch).last().FiscalDayOpened)
   time=int(time.timestamp())
   close_time=time+24*60*60
   print(close_time-time)
   now=datetime.datetime.now()
   now=int(now.timestamp())
   print(close_time-now)
   return JsonResponse({"time":close_time-now},safe=False)
  except Exception as e:
   print(str(e))
   return HttpResponse(403)
