from django.http import JsonResponse,HttpResponse
import json
from django.contrib.auth.hashers import check_password
from django.views.decorators.csrf import csrf_exempt
import logging
from .models import User, Shift
from django.contrib.auth import logout,login
from fiscalization.models import FiscalBranch
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.contrib.auth.models import Group
import datetime
from django.contrib.auth import authenticate
logging.basicConfig(
    
    filename="debug.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

@csrf_exempt
def log_out(request):
    shift=Shift.objects.get(
        user=request.user,
        ended=None
    )
    shift.ended=datetime.datetime.now()
    logout(request)  # This clears the session
    
    return HttpResponse(status=200)  # Or redirect to home page or any other page

def authenticate_from_database(username, password):
   
    try:

        user = User.objects.filter(username=username)
       
        if check_password(password, user.first().password):
            
            return True,user
        else:
            return False,user
    except Exception as e:
        print(str(e))
        return False,None
@csrf_exempt
def log_in(request):
    
    try:  
      if request.method == 'POST':
        logging.info(request.POST)
        print(request.body)
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')
        branch=data.get("branch")
        request.session["branch"]=branch
        request.modified=True
        print(username,password)
       
        success,user= authenticate_from_database(username=username, password=password)
        if success:
            login(request,user=user.first())
            import datetime
            try:
             shift,_=Shift.objects.get_or_create(
               user=request.user,
               ended=None
             )
             shift.started= datetime.datetime.now()
             shift.save()
            except Exception as e:
                print(str(e))
            try:
                print("fiscalized")
                branch=FiscalBranch.objects.get(id=request.session["branch"])
                return HttpResponse(status=201)
            except Exception as e:
                print(str(e))
                return HttpResponse(status=200)
        elif user is None:
            return HttpResponse(404)
        else:
            return HttpResponse(500)
    except Exception as e:
        print(str(e))


@csrf_exempt
def create_user(request):
    try:
        if request.method != "POST":
            return JsonResponse({"error": "Only POST allowed"}, status=405)
        print(request.POST)
        data = request.POST
        email = data.get("email")
        password = data.get("password")
        firstname = data.get("firstname")
        lastname = data.get("lastname")
        username = data.get("username")
        group_name = data.get("group")  # "Admin" or "Cashier"

        if not email or not password:
            return JsonResponse({"error": "Email and password are required"}, status=400)

        try:
            
            user = User.objects.get(email=email)
            if not hasattr(user, "initialized") or user.initialized is False:
                user.set_password(password)
                user.save()
                return JsonResponse({"success": "Password set for existing user"})
            else:
                return JsonResponse({"error": "User already has a password"}, status=400)
        except User.DoesNotExist:
            user = User.objects.create(
                email=email,
                first_name=firstname,
                last_name=lastname,
                username=username,
                role=group_name
            )
            user.set_password(password)
            user.save()

            if group_name:
                try:
                    group = Group.objects.get(name=group_name)
                    user.groups.add(group)
                except Group.DoesNotExist:
                    return JsonResponse({"error": f"Group '{group_name}' does not exist"}, status=400)

            return JsonResponse({"success": "User created successfully"})

    except Exception as e:
        print(str(e))
        return JsonResponse({"error": str(e)}, status=500)
