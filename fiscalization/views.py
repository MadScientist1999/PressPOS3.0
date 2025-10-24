import os
import json
import time

import datetime
import threading
import requests

from .encryption import sign_data,hash_data
from django.db import connection
from django.http import (
    HttpResponse,
    JsonResponse,
)
from django.views.decorators.csrf import csrf_exempt
from .models import *
from .encryption import createCertificateRequest, openssl
from django.views.decorators.csrf import csrf_exempt
import datetime
from fiscalization.models import FiscalBranch
import json
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def submit_receipt(base_url,certificate_path,private_path,data):
 
 headers = {
        "Content-Type": "application/json",
        "DeviceModelName": "Server",  # Replace with actual device name
        "DeviceModelVersion": "v1"  # Replace with actual device version
    }

 
 url=base_url+"SubmitReceipt"
 print(url)
 try:
   
  response = requests.post(cert=(certificate_path,private_path),verify=False,url=base_url+"SubmitReceipt", headers=headers, data=data)
  print(response.content)
  return response.content
 except Exception as e:    			
  print(str(e))
  
def register(request):
    # Create a folder with the specified path if it doesn't exist
    directory_path = certificates_path
    
    activation=request.POST.get("activation")
    
    if not os.path.exists(directory_path):
        os.makedirs(directory_path)

    certificateRequest = createCertificateRequest(f'ZIMRA-{request.session["branch_config"]["serial"]}-{request.session["branch_config"]["device_id"]}',request.session["branch_config"]["serial"])
    url = f'https://fdmsapitest.zimra.co.zw/Public/v1/{request.session["branch_config"]["device_id"]}/RegisterDevice'
    header = {
        'accept': 'application/json',
        'DeviceModelName': 'Server',
        'DeviceModelVersion': 'v1',
        'Content-Type': 'application/json'
    }
    data = {
        "certificateRequest": certificateRequest,
        "activationKey": activation
    }

    response = requests.post(url, headers=header, json=data)
    response_json = response.json()

    try:
        operationID = response_json['operationID']
        certificate = response_json['certificate'].replace('\\n', '\n')
    except Exception:
        certificate = ""  

    # Save files in the specified directory
    with open(os.path.join(directory_path, f'{request.session["branch_config"]["serial"]}_ToperationID.pem'), 'w') as file:
        file.write(operationID)

    with open(os.path.join(directory_path, f'{request.session["branch_config"]["serial"]}_Tcertificate.pem'), 'w') as file:
        file.write(certificate)

    try: 
        openssl(request.session["branch_config"]["serial"])
    except Exception as e:
        print(str(e))

    return response_json


@csrf_exempt
def get_config_view(request):
      # Configuration
  try:
    
    
    headers = {
    "Content-Type": "application/json",
    "DeviceModelName": "Server",
    "DeviceModelVersion": "v1",
    }
    branch=FiscalBranch.objects.get(id=request.session["branch"])
    api_endpoint_get_config = branch.base_url+"GetConfig"
    certificate_path=branch.certificate.path
    private_path=branch.private_key.path
        
    try:
        # Make the HTTPS request with the SSL context
        response = requests.get(api_endpoint_get_config, headers=headers, cert=(certificate_path,private_path), verify=False)  # SSL verification can be disabled if necessary

        # Process the response
        if response.status_code == 200:
            data = response.json()
            data["pending"]=FiscalReceipt.objects.filter(submited=False).count()
            data["device_id"]=branch.device_id
            return JsonResponse(data)
        else:
            print(response.json())
            return JsonResponse({"error": interpret_code(response.status_code)}, status=response.status_code)
    except requests.exceptions.RequestException as e:
        print(str(e))
        return JsonResponse({"error": f"Connection error: {str(e)}"}, status=500)
    except Exception as e:
        print(str(e))
        print("Internal error")
        return JsonResponse({"error": f"Internal error: {str(e)}"}, status=500)
  except Exception as e:
    print(str(e))
    

def interpret_code(status_code):
    #Interpret HTTP status codes into error messages.
    
    errors = {
        400: "Bad request - the message is malformed and could not be processed by Fiscal Backend Gateway.",
        401: "Authentication error.",
        404: "Resource not found.",
        405: "Method not allowed - unsupported HTTP method.",
        422: "Unprocessable Content - instructions given by the fiscal device are incorrect.",
    }
    return errors.get(status_code, "Unknown error")

@csrf_exempt
def get_status_view(request):
 
  try:   # Configuration
    branch=FiscalBranch.objects.get(id=request.session["branch"])
    api_endpoint_get_status = branch.base_url+"GetStatus/"
    certificate_path=branch.certificate.path
    private_path=branch.private_key.path
    
    print(api_endpoint_get_status)
    
    headers = {
    "Content-Type": "application/json",
    "DeviceModelName": "Server",
    "DeviceModelVersion": "v1",
   }
  
    try:
       
        # Make the HTTPS request with the SSL context
        response = requests.get(api_endpoint_get_status, headers=headers, cert=(certificate_path,private_path), verify=False)  # SSL verification can be disabled if necessary
        
        # Process the response
        if response.status_code == 200:
            data = response.json()
            return JsonResponse(data)
        else:
            print(response.content)
            print(response.json())
            return JsonResponse({"error": interpret_code(response.status_code)}, status=response.status_code)
    except requests.exceptions.RequestException as e:
        print(str(e))
        return JsonResponse({"error": f"Connection error: {str(e)}"}, status=400)
    except Exception as e:
        print(str(e))
        return JsonResponse({"error": f"Internal error: {str(e)}"}, status=500)
  except Exception as e:
    print(str(e))

@csrf_exempt
def open_day_view(request):
    branch=FiscalBranch.objects.get(id=request.session["branch"])
    # Initialize response
    get_open_day_server_response = "There was no response from the server"
    api_endpoint_openday = branch.base_url+"OpenDay"
    # Get the latest receipt information
    
    try:
        with connection.cursor() as cursor:
            
            status=get_status_view(request)
            
            print(status.content)
            status=json.loads(status.content)
            try:
             fiscal_day_no=status['lastFiscalDayNo']+1
            except:
             fiscal_day_no=1
            closed=status["fiscalDayStatus"]=="FiscalDayClosed"
            opened=not status["fiscalDayStatus"]=="FiscalDayClosed"
            
            if opened:
                return JsonResponse({"response":"Day already open"},status=404)
            
            if closed:
                
                openday=OpenDay.objects.filter(open=True,branch=branch).last()
                print(openday)
                if not openday is None:
                 openday.FiscalDayClosed="ManualClose"
                 openday.open=False
                 openday.save()
                
            
    except Exception as e:
        return JsonResponse({'error': str(e)},status=500)

  
     

    # Prepare current timestamp and OpenDay request
    now = datetime.datetime.now()
    iso8601 = now.strftime('%Y-%m-%dT%H:%M:%S')
    

 

    # Send OpenDay request to the server
    headers = {
        "Content-Type": "application/json",
        "DeviceModelName": "Server",  # Replace with actual device name
        "DeviceModelVersion": "v1"  # Replace with actual device version
    }
    
    
    # Define file paths
    
    try:
        certificate_path=branch.certificate.path
        private_path=branch.private_key.path
        Dtime=datetime.datetime.now().isoformat(sep="T",timespec="seconds")
        
        response = requests.post(api_endpoint_openday,cert=(certificate_path,private_path), json={"fiscalDayOpened":Dtime,"device_id":branch.device_id}, headers=headers, verify=False)  # SSL verification can be disabled if necessary
        print("Device OpenDay request sent")
        if response.status_code == 200:
            get_open_day_server_response = response.json()  # Assuming response is JSON
            print("OpenDay has been POSTED successfully")
             # Save OpenDay data to the database
            try:
                openday=OpenDay.objects.create(
                FiscalDayNo=fiscal_day_no,
                FiscalDayOpened=iso8601,
                FiscalDayClosed="",
                counter=1,
                branch=branch
                )
                DailyReports.objects.create(FiscalDay=openday)
                
                print("OpenDay data submitted to database")
            except Exception as e:
                print("Error saving OpenDay data:", str(e))
        else:
            print(response.status_code)
            print(response.json())
            print("OpenDay has NOT been POSTED, probable issue with parameters sent to server")
    except requests.exceptions.RequestException as e:
        print(response.status_code)
        print("Error in OpenDay request:", str(e))

   

    # Return the server response
    return JsonResponse({"response": get_open_day_server_response})

@csrf_exempt
def close_day_view(request):
   try:
    from .signals import processing_threads,submitAll
    branch=FiscalBranch.objects.get(id=request.session["branch"])
    
    submitAll(request)
    thread=processing_threads.get(branch.name)
    if thread and thread.is_alive():
     while thread.is_alive():
       time.sleep(0.5)
   
    api_endpoint_closeday = branch.base_url+"CloseDay"
    last_report=DailyReports.objects.filter(FiscalDay__branch=branch).last()
    try:
     openday=last_report.FiscalDay
    except:
     return JsonResponse({"error":"Cant close day without any transactions"},status=500)
    dateOpened=openday.FiscalDayOpened.split("T")[0]
    concatenated_counters=last_report.__str__(branch.production)
    string_to_implement = f"{branch.device_id}{openday.FiscalDayNo}{dateOpened}{concatenated_counters}"

    try:
        with connection.cursor() as cursor:

            status=get_status_view(request)
            print(status.content)
            status=json.loads(status.content)
            fiscal_day_no=status['lastFiscalDayNo']
            closed=status["fiscalDayStatus"]=="FiscalDayClosed"
            openday.FiscalDayNo=fiscal_day_no
            if closed:
                openday.FiscalDayClosed="ManualClose"
                openday.open=0
                openday.save(using=request.session["branch"])
                return JsonResponse({"response":"Day already closed"})
            
    except Exception as e:
        return JsonResponse({'error': str(e)},status=500)     
    headers = {
        "Content-Type": "application/json",
        "DeviceModelName": "Server",  # Replace with actual device name
        "DeviceModelVersion": "v1"  # Replace with actual device version
    }
    print(string_to_implement)
    signature=sign_data(branch,string_to_implement)
    hash_value=hash_data(string_to_implement)       
    headers = {
            
            'DeviceModelName': "Server",
            'DeviceModelVersion':"v1",
            'accept': 'application/json',
            'Content-Type': 'application/json'
        }

    
    payload = {
            "deviceID": branch.device_id,
            "fiscalDayNo": fiscal_day_no,
            "fiscalDayCounters": last_report.to_dict(branch.production) ,
            "fiscalDayDeviceSignature": {
                "hash": hash_value,
                "signature": signature
            },
            "receiptCounter": openday.counter-1
        }
    
    

    payload=json.dumps(payload)
    print(payload)
    try:

            certificate_path=branch.certificate.path
            private_path=branch.private_key.path
            response = requests.post(
                api_endpoint_closeday, 
                headers=headers,
                cert=(certificate_path, private_path),
                verify=False,
                data=payload
            )
            print(response.json())
            response.raise_for_status()
            print(response) 
            start_status_check_thread(request)
             
            return get_status_view(request)

    except requests.exceptions.RequestException as e:
         return HttpResponse(f"HTTP request failed: {e}")
    except ValueError:
         return HttpResponse(f"Invalid JSON response")
   except Exception as e:
    print(str(e))
    return JsonResponse({"error": f"Internal error: {str(e)}"}, status=500)


def check_fiscal_day_status(request):
    #Repeatedly checks the fiscal day status until closed or failed.
    try:
     status=get_status_view(request)
    except Exception as e:
       print(str(e))
    statusOG=get_status_view(request)
    
    statusOG=json.loads(status.content)["fiscalDayStatus"]
    while True:
        try:
                status=get_status_view(request)
                print(status.content)
                status=json.loads(status.content)["fiscalDayStatus"]
                print(status)
                if not status == statusOG:
                    break
                

        except Exception as e:
            print("Error checking fiscal status:", e)

        time.sleep(4)  # wait 3 seconds before checking again

def start_status_check_thread(request):
    
    #Starts the background thread.
    
    thread = threading.Thread(
        target=check_fiscal_day_status,
        args=(request,),
        daemon=True  # optional: stops with main program
    )
    thread.start()

@csrf_exempt
def time_to_close(request):
  try: 
   time=datetime.datetime.fromisoformat(OpenDay.objects.using(request.session["branch"]).filter(open=1).last().FiscalDayOpened)
   
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
