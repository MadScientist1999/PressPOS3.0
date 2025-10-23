import os
import json
import time
import logging
import datetime
import threading
import requests
import re
from main.models import Shift
import qrcode
from pos.other import generate_invoice_code
from pos.models import TransactionStock,BankingDetails
from pos.pretransactions import presale_procedure,precredit_procedure,predebit_procedure
from .encryption import sign_data,hash_data,get_first16chars_of_signature
from django.db import connection
from django.http import (
    HttpResponse,
    FileResponse,
    JsonResponse,
)

from django.views.decorators.csrf import csrf_exempt
from django.template.loader import render_to_string
from .models import *
from .encryption import createCertificateRequest, openssl
from django.shortcuts import render
from pos.models import Branch
from django.http import JsonResponse,HttpResponse,FileResponse
from django.views.decorators.csrf import csrf_exempt
import datetime
from fiscalization.models import FiscalBranch
import json
import logging
from pos.saver import save
from decimal import Decimal, ROUND_HALF_UP
from django.template.loader import render_to_string
import urllib3
from main.settings import HTML_ROOT
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
@csrf_exempt
def credit_fiscal_sale(request,receipt_id):
   try:
   
    # Validate license
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)
    branch=FiscalBranch.objects.get(id=request.session["branch"])
    openday=OpenDay.objects.get(open=True,branch=branch)
    if openday is None:
       return HttpResponse(status=400)
    
    receipt=FiscalReceipt.objects.get(id=receipt_id)
    
    data = precredit_procedure(request,receipt)  # 👈 Parse body JSON
    
    user=data.get("user")
    reason=data.get("reason")
    if receipt.serverResponse is None:
        from .signals import submitAll,processing_locks
        submitAll(request)
        if not processing_locks[branch.name].acquire(timeout=10):
            print("Submitted All")
        
    customer=receipt.customer
    currency=receipt.currency
    items=receipt.invoiceItems
    previousReceiptHash=openday.previousReceiptHash
    counter=openday.counter
    globalNo=branch.globalNo
    receipt_day=data.get("receipt_day")
    Dtime=data.get("Dtime")
    date=data.get("date")
    time=data.get("time")
    year=date.split("-")[0]
    month=date.split("-")[1]
    day=date.split("-")[2]
    products=data.get("products")
    receiptID=json.loads(receipt.serverResponse)["receiptID"]
    receiptJsonBody=json.loads(receipt.receiptJsonbody)["receipt"]
    receipt_day=receipt.day   
    for tax_line in receiptJsonBody["receiptTaxes"]:
        tax_line["SalesAmountwithTax"]*=-1
        tax_line["taxAmount"]=float(tax_line['taxAmount'])*-1
    receiptJsonBody["receiptPayments"][0]["paymentAmount"]=f"{-1*float(receiptJsonBody['receiptPayments'][0]['paymentAmount'])}"
    for receiptLine in receiptJsonBody["receiptLines"]:
          receiptLine["receiptLineTotal"]=receiptLine['receiptLineTotal']*-1
          receiptLine["receiptLinePrice"]=f"{float(receiptLine['receiptLinePrice'])*-1}"
    try:
        creditJson={"creditDebitNote":{"receiptGlobalNo":f"{receipt.receiptGlobalNo}","fiscalDayNo":f"{receipt_day.FiscalDayNo}","receiptID":f"{receiptID}","deviceID":branch.device_id},"receiptLines":receiptJsonBody["receiptLines"],"receiptTaxes":receiptJsonBody["receiptTaxes"],"receiptNotes":reason,"receiptTotal":-1*receiptJsonBody["receiptTotal"],"receiptLinesTaxInclusive":True,"invoiceNo":receipt.invoiceNo.replace("FI","FC"),"receiptCurrency":receipt.currency.symbol,"receiptPrintForm":"InvoiceA4" if receipt.isA4 else "Receipt48","receiptType":"CREDITNOTE","receiptGlobalNo":globalNo,"receiptDate":Dtime,"receiptPayments":receiptJsonBody["receiptPayments"]}
    except Exception as e:
        print(str(e))  
    
    if not customer is None:
        print(customer.name)
        creditJson["buyerData"]={"VATNumber": customer.vat_number, "buyerTradeName": customer.tradename, "buyerTIN": customer.tin_number, "buyerRegisterName": customer.name,"buyerAddress":{"province":customer.province,"city":customer.city,"houseNo":customer.address,"street":customer.street},"buyerContacts":{"phoneNo":customer.phone_number,"email":customer.email}} 
    
    print("3")      
    tax_lines=creditJson["receiptTaxes"]
    tax_lines_concat=""
    
    for taxline in tax_lines:
        try:
            taxPercentForConcat = "15.00" if float(taxline.get("taxPercent", 0)) == 15.0 else "0.00"
            print(taxPercentForConcat)
            tax_lines_concat += (
            f"{taxline['taxCode']}"
            f"{taxPercentForConcat}"
            f"{round(float(taxline['taxAmount']) * 100)}"
            f"{round(float(taxline['SalesAmountwithTax']) * 100)}"
        )
        except Exception as e:
            tax_lines_concat += f"{taxline['taxCode']}0{round(float(taxline.get('SalesAmountwithTax', 0)) * 100)}"
            print(str(e))

    type="CREDITNOTE"
    total=int(float(receipt.total)*-100)
    result_string = f"{branch.device_id}{type}{currency}{globalNo}{Dtime}{total}{tax_lines_concat}{previousReceiptHash}"
    signature=sign_data(branch,result_string)
    receipt_hash_base64=hash_data(result_string)
    md5_hash=get_first16chars_of_signature(signature)
    md5_hash_16=md5_hash[:16]
    creditJson["receiptDeviceSignature"]={"signature":signature,"hash":receipt_hash_base64}     
    creditJson["receiptCounter"]=counter
  
    # Invoice numbering
    last_number = re.sub(r"[a-zA-Z]", "", receipt.invoiceNo).replace("-","")
    
    credit = FiscalCredit.objects.create(
             # Same ID as the original Receipt
            currency=receipt.currency,
            invoiceNo=f"FC{last_number}-{generate_invoice_code()}",
            receiptGlobalNo=globalNo,
            receiptCounter=counter,
            date=date,
            time=time,
            receipt_type="CREDIT NOTE",  # Credit type
            subtotal=receipt.subtotal,
            tax=receipt.tax,
            total=receipt.total,
            payment=receipt.payment,
            isA4=receipt.isA4,
            customer=customer,
            Total15VAT=receipt.Total15VAT,
            TotalNonVAT=receipt.TotalNonVAT,
            TotalExempt=receipt.TotalExempt,
            invoiceItems=items,
            profitBT=receipt.profitBT,
            profitAT=receipt.profitAT,
            payment_method=receipt.payment_method,
            reason=reason,  # Adding the reason for credit note
            user=user,
            fiscal_receipt=receipt,
            fiscal_branch=branch,
            branch=Branch.objects.get(id=request.session["branch"]),
            receiptJsonbody=json.dumps({"receipt":creditJson}),
            signature=signature,
            md5_hash=md5_hash,
            result_string=result_string,
            receiptHash=receipt_hash_base64,
            day=openday,
            qrurl=f"https://{'fdms' if branch.production else 'fdmstest'}.zimra.co.zw/{branch.device_id.zfill(10)}{day}{month}{year}{globalNo:010}{md5_hash_16}"
        )
    credit.products.set(receipt.products.all())
    credit.save()
    qr = qrcode.QRCode(
          version=1,  # Controls the size (1 = smallest, 40 = largest)
          error_correction=qrcode.constants.ERROR_CORRECT_L,  # Low error correction
          box_size=4,  # Size of each QR box
          border=1,  # Border thickness
          )
    qr.add_data(credit.qrurl)
    qr.make(fit=True)
    img = qr.make_image(fill="black", back_color="white")
    img.save(f"{HTML_ROOT}/{branch.name}_{credit.invoiceNo}.png")  # Saves the QR code as an image
    try: 
        openday.previousReceiptHash=credit.receiptHash
        branch.globalNo=credit.receiptGlobalNo+1
    except Exception as e:
             print(str(e))        
          
    openday.counter+=1
    receipt.credited=True      
    if(credit.currency.symbol=="USD"):
        openday.no_of_credits_usd+=1
    else:
        openday.no_of_credits_zwl+=1
    receipt.save()
    openday.save()
    branch.save() 
    try:
        banking_details=BankingDetails.objects.filter(stackholder=branch.company.stackholder_ptr_id,currency=currency).first()
    except:
        banking_details=None       
    try:
        # 1️⃣ Render main HTML directly
        html_content = render_to_string("sale_complete.html", {
            "payment": credit.payment,
            "username": user.username,
            "change": round(float(credit.payment) - float(credit.total), 2),
            "invoice": json.loads(credit.invoiceItems)["invoiceItems"],
            "selectedCurrencySymbol": credit.currency.symbol,
            "subtotal": credit.subtotal,
            "tax": credit.tax,
            "invoiceNo": credit.invoiceNo,
            "type": "CREDIT NOTE",
            "total": credit.total,
            "date": date,
            "time": time,
            "products": products,
            "customer": credit.customer if credit.customer else None,
            "currencySymbol": credit.currency.symbol,
            "payment_method": credit.payment_method,
            "reason": reason,
            "referenceNo": receipt.invoiceNo,
            "change": receipt.payment - receipt.total,
            "branch": branch,
            "size": "A4" if receipt.isA4 else "80mm",
            "qrpath": f"{HTML_ROOT}/{branch.name}_{credit.invoiceNo}.png",
            "qrurl": branch.base_url,
            "verificationCode": credit.md5_hash,
            "deviceID": branch.device_id,
            "globalNo": credit.receiptGlobalNo,
            "FiscalDay": openday.FiscalDayNo,
        })
        if receipt.isA4:
            # 2️⃣ Render footer HTML depending on A4 or 80mm
            footer_html = render_to_string(
            "footerA4.html",
            {
                "qrpath": f"{HTML_ROOT}/{branch.name}_{credit.invoiceNo}.png",
                "qrurl": branch.base_url,
                "verificationCode": credit.md5_hash,
                "deviceID": branch.device_id,
                "globalNo": credit.receiptGlobalNo,
                "FiscalDay": openday.FiscalDayNo,
                "bank": banking_details
            })
            header_context = {
             "branch": branch,
             "user": receipt.user,
                }

            if branch.logo.path:
                header_context["logo"] = branch.logo.path
            
            header_html = render_to_string("headerA4.html", header_context)
            
              
        else:
                footer_html=None
                header_html=None
        print("HIHIAHIH")   
        # 3️⃣ Generate PDF using save(), passing both HTMLs
        pdf_path = save(html_content=html_content, filename=f"{branch.name}_{credit.invoiceNo}", footer_html=footer_html,header_html=header_html)
          
        # 4️⃣ Save PDF path and products
        if os.path.exists(pdf_path):
            credit.file = pdf_path
            credit.products.set(products)
            credit.save()
            return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')

    except Exception as e:
        print(str(e))
        logging.info(f"Exception occurred: {str(e)}")
        return JsonResponse({"error": "Failed to complete sale. Please try again."}, status=500)

    except Exception as e:
        print(str(e))
        logging.info(f"Exception occurred: {str(e)}")
        return JsonResponse({"error": "Failed to complete sale. Please try again."}, status=500)
   except Exception as e:
       print(str(e))
       logging.info(str(e))
       return HttpResponse(500)
@csrf_exempt
def debit_fiscal_sale(request,receipt_id):
  
    # Validate license
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    
    receipt=FiscalReceipt.objects.get(id=receipt_id)
    if receipt.serverResponse is None:
        from .signals import submitAll,processing_locks
        submitAll(request)
        if not processing_locks[branch.name].acquire(timeout=10):
            print("Submitted All")
    
    
    branch=FiscalBranch.objects.get(id=request.session["branch"])
    openday=OpenDay.objects.get(open=True,branch=branch)
    if openday is None:
       return HttpResponse(status=400)
    
    data=predebit_procedure(request,receipt)
    user=data.get("user")
    customer=receipt.customer
    reason=data.get("reason")
    currency=receipt.currency
    products=data.get("products")
    previousReceiptHash=openday.previousReceiptHash
    counter=openday.counter
    globalNo=branch.globalNo
    receipt_day=receipt.day
    Dtime=data.get("now")
    date=data.get("date")
    time=data.get("time")
    year=date.split("-")[0]
    month=date.split("-")[1]
    day=date.split("-")[2]
    
    try:
      receiptID=json.loads(receipt.serverResponse)["receiptID"]
    except:
      receiptID=""
    receiptJsonBody=json.loads(receipt.receiptJsonbody)["receipt"]
    try:
        debitJson={"creditDebitNote":{"receiptGlobalNo":f"{receipt.receiptGlobalNo}","fiscalDayNo":f"{receipt_day.FiscalDayNo}","receiptID":f"{receiptID}","deviceID":branch.device_id},"receiptLines":receiptJsonBody["receiptLines"],"receiptTaxes":receiptJsonBody["receiptTaxes"],"receiptNotes":reason,"receiptTotal":receiptJsonBody["receiptTotal"],"receiptLinesTaxInclusive":True,"invoiceNo":receipt.invoiceNo.replace("FI","FD"),"receiptCurrency":receipt.currency.symbol,"receiptPrintForm":"InvoiceA4" if receipt.isA4 else "Receipt48","receiptType":"DEBITNOTE","receiptGlobalNo":globalNo,"receiptDate":Dtime,"receiptPayments":receiptJsonBody["receiptPayments"]}
    except Exception as e:
        print(str(e))  
    
    if not customer is None:
        print(customer.name)
        debitJson["buyerData"]={"VATNumber": customer.vat_number, "buyerTradeName": customer.tradename, "buyerTIN": customer.tin_number, "buyerRegisterName": customer.name,"buyerAddress":{"province":customer.province,"city":customer.city,"houseNo":customer.address,"street":customer.street},"buyerContacts":{"phoneNo":customer.phone_number,"email":customer.email}} 
    
    print("3")      
    tax_lines=debitJson["receiptTaxes"]
    tax_lines_concat=""
    
    for taxline in tax_lines:
        try:
            taxPercentForConcat = "15.00" if float(taxline.get("taxPercent", 0)) == 15.0 else "0.00"
            print(taxPercentForConcat)
            tax_lines_concat += (
            f"{taxline['taxCode']}"
            f"{taxPercentForConcat}"
            f"{round(float(taxline['taxAmount']) * 100)}"
            f"{round(float(taxline['SalesAmountwithTax']) * 100)}"
        )
        except Exception as e:
            tax_lines_concat += f"{taxline['taxCode']}0{round(float(taxline.get('SalesAmountwithTax', 0)) * 100)}"
            print(str(e))

    type="DEBITNOTE"
    total=int(float(receipt.total)*100)
    result_string = f"{branch.device_id}{type}{currency}{globalNo}{Dtime}{total}{tax_lines_concat}{previousReceiptHash}"
    signature=sign_data(branch,result_string)
    receipt_hash_base64=hash_data(result_string)
    md5_hash=get_first16chars_of_signature(signature)
    md5_hash_16=md5_hash[:16]
    debitJson["receiptDeviceSignature"]={"signature":signature,"hash":receipt_hash_base64}     
    debitJson["receiptCounter"]=counter
    
    last_number = re.sub(r"[a-zA-Z]", "", receipt.invoiceNo).replace("-","")
    
    debit = FiscalDebit.objects.create(
             # Same ID as the original Receipt
            currency=receipt.currency,
            invoiceNo=f"FD{last_number}-{generate_invoice_code()}",
            receiptGlobalNo=globalNo,
            receiptCounter=counter,
            date=date,
            time=time,
            receipt_type="DEBIT NOTE",  # Debit type
            subtotal=receipt.subtotal,
            tax=receipt.tax,
            total=receipt.total,
            payment=receipt.payment,
            isA4=receipt.isA4,
            customer=customer,
            Total15VAT=receipt.Total15VAT,
            TotalNonVAT=receipt.TotalNonVAT,
            TotalExempt=receipt.TotalExempt,
            invoiceItems=receipt.invoiceItems,
            profitBT=receipt.profitBT,
            profitAT=receipt.profitAT,
            payment_method=receipt.payment_method,
            reason=reason,  # Adding the reason for credit note
            user=user,
            fiscal_receipt=receipt,
            branch=Branch.objects.get(id=request.session["branch"]),
            fiscal_branch=branch,
            receiptJsonbody=json.dumps({"receipt":debitJson}),
            signature=signature,
            md5_hash=md5_hash,
            result_string=result_string,
            receiptHash=receipt_hash_base64,
            day=openday,
            qrurl=f"https://{'fdms' if branch.production else 'fdmstest'}.zimra.co.zw/{branch.device_id.zfill(10)}{day}{month}{year}{globalNo:010}{md5_hash_16}"
        )
    
    qr = qrcode.QRCode(
          version=1,  # Controls the size (1 = smallest, 40 = largest)
          error_correction=qrcode.constants.ERROR_CORRECT_L,  # Low error correction
          box_size=4,  # Size of each QR box
          border=1,  # Border thickness
          )
    qr.add_data(debit.qrurl)
    qr.make(fit=True)
    img = qr.make_image(fill="black", back_color="white")
    img.save(f"{HTML_ROOT}/{branch.name}_{debit.invoiceNo}.png")  # Saves the QR code as an image
    try: 
        openday.previousReceiptHash=debit.receiptHash
        branch.globalNo=debit.receiptGlobalNo+1
    except Exception as e:
             print(str(e))        
          
    openday.counter+=1
    receipt.debited=True      
    if(debit.currency.symbol=="USD"):
        openday.no_of_credits_usd+=1
    else:
        openday.no_of_credits_zwl+=1
    receipt.save()
    openday.save()
    branch.save() 
    try:
        banking_details=BankingDetails.objects.filter(stackholder=branch.company.stackholder_ptr_id,currency=currency).first()
    except:
        banking_details=None     
    try:
    # 1️⃣ Render main HTML for debit note
        html_content = render_to_string("sale_complete.html", {
            "payment": debit.payment,
            "username": user.username,
            "change": round(float(debit.payment) - float(debit.total), 2),
            "invoice": json.loads(debit.invoiceItems)["invoiceItems"],
            "selectedCurrencySymbol": debit.currency.symbol,
            "subtotal": debit.subtotal,
            "tax": debit.tax,
            "invoiceNo": debit.invoiceNo,
            "type": "DEBIT NOTE",
            "total": debit.total,
            "date": date,
            "time": time,
            "products": products,
            "customer": debit.customer if debit.customer else None,
            "myCompany": branch.company,
            "currencySymbol": debit.currency.symbol,
            "payment_method": debit.payment_method,
            "reason": reason,
            "referenceNo": receipt.invoiceNo,
            "change": receipt.payment - receipt.total,
            "branch": branch,
            "size": "A4" if receipt.isA4 else "80mm",
            "qrpath": f"{HTML_ROOT}/{branch.name}_{debit.invoiceNo}.png",
            "qrurl": branch.base_url,
            "verificationCode": debit.md5_hash,
            "deviceID": branch.device_id,
            "globalNo": debit.receiptGlobalNo,
            "FiscalDay": openday.FiscalDayNo,
            })
        if receipt.isA4:
            # 2️⃣ Render footer HTML depending on A4 or 80mm
            footer_html = render_to_string(
            "footerA4.html",
            {
                "qrpath": f"{HTML_ROOT}/{branch.name}_{debit.invoiceNo}.png",
                "qrurl": branch.base_url,
                "verificationCode": debit.md5_hash,
                "deviceID": branch.device_id,
                "globalNo": debit.receiptGlobalNo,
                "FiscalDay": openday.FiscalDayNo,
                "bank": banking_details
            }
            )
            header_context = {
             "myCompany": branch.company,
             "branch": branch,
             "user": receipt.user,
                }

            if branch.logo.path:
                header_context["logo"] = branch.logo.path
            
            header_html = render_to_string("headerA4.html", header_context)
            
                
              
        else:
            footer_html=None
            header_html=None
                
        # 3️⃣ Generate PDF using save(), passing both HTMLs
        pdf_path = save(html_content=html_content, filename=f"{branch.name}_{debit.invoiceNo}", footer_html=footer_html,header_html=header_html)
          
        # 4️⃣ Save PDF path and products
        if os.path.exists(pdf_path):
            debit.file = pdf_path
            debit.products.set(products)
            debit.save()
            return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')

    except Exception as e:
        print(str(e))
        logging.info(f"Exception occurred: {str(e)}")
        return JsonResponse({"error": "Failed to complete sale. Please try again."}, status=500)

    

# Create your views here.
@csrf_exempt
def make_fiscal_sale(request):
    # Validate license
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    try:
        data = presale_procedure(request)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    branch = FiscalBranch.objects.get(id=request.session["branch"])
    
    openday = OpenDay.objects.filter(open=True, branch=branch).last()
    if openday is None:
       print(openday)
       return HttpResponse(status=400)
    print(data)
    # Extract fields
    customer= data.get("customer")
    if customer:
        if customer.customer_type=="individual":
            customer.tin_number="0000000000"
            customer.vat_number="000000000"
    items = data.get("invoice_items", [])
    currency= data.get("currency")
    payment = data.get("payment")
    print_format = data.get("print_format")
    payment_method = data.get("payment_method")
    mobile_methods = ["Ecocash", "OneMoney", "InnBucks", "Mukuru", "Telecash"]
    Dtime = data.get("now")
    user = request.user
    comment=data.get("comment")
    is_a4 = data.get("is_a4")
    date_str=data.get("date_str")
    time_str = data.get("time_str")
    products = data.get("products")
    inc_total = data.get("inc_total")
    exc_total=data.get("exc_total")
    profit_at=data.get("profit_at")
    profit_bt=data.get("profit_bt")
    total_15 = data.get("total_15")
    total_0 = data.get("total_0")
    on_account=data.get("on_account")
    total_exempt = data.get("total_0")
    tax_total=data.get("tax_total")
    used_stock_entries=data.get("used_stock_entries")
    receipt_lines=data.get("receipt_lines")
    receiptTaxes = []
    profit_at=0
    profit_bt=0
    salesamountwithtax = total_15
    import re
    # Invoice numbering
    last_receipt = FiscalReceipt.objects.order_by('-invoiceNo').first()
    try:
     last_number = int(re.sub(r"[a-zA-Z]", "", last_receipt.invoiceNo))
    except:
     last_number=0
    invoiceNo = f"FI{last_number + 1}"

    # Prepare receipt taxes
    def append_tax(taxID, code, percent, amount, sales_with_tax):
            receiptTaxes.append({
                "taxID": taxID,
                "taxCode": code,
                "taxPercent": percent,
                "taxAmount": round(float(amount), 2) if percent else "0",
                "SalesAmountwithTax": float(sales_with_tax)
            })
    
    if not branch.production:
        if total_exempt>0:
         append_tax("1", "A", None, 0, total_exempt) 
        
        if total_0>0:
         append_tax("2", "B", 0.00, 0, total_0) 
        
        if salesamountwithtax>0:
         append_tax("3", "C", 15.00, tax_total, salesamountwithtax) 
    else:
        if salesamountwithtax>0:
         append_tax("1", "A", 15.00, tax_total, salesamountwithtax) 
        if total_0>0:
         append_tax("2", "B", 0.00, 0, total_0) 
        if total_exempt>0:
         append_tax("3", "C", None, 0, total_exempt) 

    # JSON body for receipt
    jsonBody = {
        "receiptLines": receipt_lines,
        "receiptType": "FISCALINVOICE",
        "receiptCurrency": currency.symbol,
        "receiptPrintForm": "InvoiceA4" if is_a4 else "Receipt48",
        "receiptDate": Dtime,
        "receiptPayments": [{"moneyTypeCode": "MobileWallet" if payment_method in mobile_methods else payment_method, "paymentAmount": round(float(inc_total), 2)}],
        "receiptTaxes": receiptTaxes,
        "receiptTotal": float(inc_total),
        "receiptLinesTaxInclusive": True,
        "invoiceNo": invoiceNo
    }

    if customer:
        jsonBody["buyerData"] = {
            "VATNumber": customer.vat_number,
            "buyerTradeName": customer.tradename,
            "buyerTIN": customer.tin_number,
            "buyerRegisterName": customer.name,
            "buyerAddress": {
                "houseNo": customer.address,
                "province": customer.province,
                "city": customer.city,
                "street": customer.street
            },
            "buyerContacts": {
                "email": customer.email,
                "phoneNo": customer.phone_number
            }
        }

    # Prepare fiscal signature
    total = int(float(inc_total * Decimal(100)))
    previousReceiptHash = openday.previousReceiptHash
    globalNo = branch.globalNo
    local_date, local_time = Dtime.split("T")
    year, month, day = local_date.split("-")

    # Concatenate tax lines
    tax_lines_concat = ""
    for taxline in receiptTaxes:
        try:
           
            print(taxline)
            taxPercentForConcat = "15.00" if float(taxline.get("taxPercent", 0)) == 15.0 else "0.00"
            print(taxPercentForConcat)
            tax_lines_concat += (
            f"{taxline['taxCode']}"
            f"{taxPercentForConcat}"
            f"{round(float(taxline['taxAmount']) * 100)}"
            f"{round(float(taxline['SalesAmountwithTax']) * 100)}"
        )
        except Exception as e:
            tax_lines_concat += f"{taxline['taxCode']}0{round(float(taxline.get('SalesAmountwithTax', 0)) * 100)}"
            print(str(e))
    type = 'FISCALINVOICE'
    result_string = f"{branch.device_id}{type}{currency.symbol}{globalNo}{Dtime}{total}{tax_lines_concat}{previousReceiptHash if openday.counter != 1 else ''}"
    signature = sign_data(branch, result_string)
    receipt_hash_base64 = hash_data(result_string)
    md5_hash_16 = get_first16chars_of_signature(signature)[:16]

    # Save and render receipt
    def save_and_render_receipt():
        try:
            last_receipt = FiscalReceipt.objects.filter(fiscal_branch=branch).last()
            fiscal_receipt = FiscalReceipt(
                isA4=is_a4,
                customer=customer,
                result_string=result_string,
                payment=payment,
                receipt_type="FISCAL TAX INVOICE",
                tax=tax_total,
                date=date_str,
                time=time_str,
                total=inc_total,
                invoiceNo=f"FI{last_receipt.id + 1}-{generate_invoice_code()}" if last_receipt else f"FI1-{generate_invoice_code()}",
                subtotal=exc_total,
                invoiceItems=json.dumps({"invoiceItems": items}),
                currency=currency,
                Total15VAT=total_15,
                TotalNonVAT=total_0,
                TotalExempt=total_exempt,
                profitAT=profit_at,
                profitBT=profit_bt,
                payment_method=payment_method,
                comment=comment,
                fiscal_branch=branch,
                user=user,
                branch=branch,
                receiptCounter=openday.counter,
                receiptGlobalNo=globalNo,
                signature=signature,
                md5_hash=md5_hash_16,
                day=openday,
                receiptHash=receipt_hash_base64,
                qrurl=f"https://{'fdms' if branch.production else 'fdmstest'}.zimra.co.zw/{branch.device_id.zfill(10)}{day}{month}{year}{globalNo:010}{md5_hash_16}",
                shift=Shift.objects.filter(user=user).last(),
                on_account=on_account
            
            )
            jsonBody["receiptDeviceSignature"] = {"signature": signature, "hash": receipt_hash_base64}
            jsonBody["receiptGlobalNo"] = fiscal_receipt.receiptGlobalNo
            jsonBody["receiptCounter"] = fiscal_receipt.receiptCounter
            jsonBody["invoiceNo"] = fiscal_receipt.invoiceNo
            fiscal_receipt.receiptJsonbody = json.dumps({"receipt": jsonBody})
            fiscal_receipt.save()
            fiscal_receipt.products.set(products)
            fiscal_receipt.save()
            # Prepare TransactionStock objects
            receipt_stock_objects = [
            TransactionStock(
            transaction=fiscal_receipt,
            stock=stock_entry,
            quantity=qty
            ) for stock_entry, qty in used_stock_entries
            ]
            print(receipt_stock_objects)
            # Bulk insert in one query
            TransactionStock.objects.bulk_create(receipt_stock_objects)
            print("here")
            # Update Temporary
            
            # Update open day counters
            openday.counter += 1
            
            if currency.symbol=="USD":
             
             openday.no_of_receipts_usd+=1
            else:
             openday.no_of_receipts_zwl+=1
            openday.previousReceiptHash=fiscal_receipt.receiptHash
            openday.save()
            branch.globalNo+=1
            branch.save()
            # Generate QR code
            qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=4, border=1)
            qr.add_data(fiscal_receipt.qrurl)
            qr.make(fit=True)
            img = qr.make_image(fill="black", back_color="white")
            img.save(f"{HTML_ROOT}/{branch.name}_{fiscal_receipt.invoiceNo}.png")
            print(products)
            # Prepare context
            try:
             banking_details=BankingDetails.objects.filter(stackholder=branch.company.stackholder_ptr_id,currency=currency).first()
            except:
             banking_details=None
            # 2️⃣ Render main invoice HTML
            html_content = render_to_string("sale_complete.html", {
            "payment": fiscal_receipt.payment,
            "username": user.username,
            "invoice": json.loads(fiscal_receipt.invoiceItems)["invoiceItems"],
            "products": products,
            "selectedCurrencySymbol": fiscal_receipt.currency.symbol,
            "subtotal": exc_total,
            "tax": tax_total,
            "invoiceNo": fiscal_receipt.invoiceNo,
            "type": "FISCAL TAX INVOICE",
            "total": inc_total,
            "date": local_date,
            "time": local_time,
            "customer": fiscal_receipt.customer,
            "myCompany": branch.company,
            "currencySymbol": fiscal_receipt.currency.symbol,
            "payment_method": fiscal_receipt.payment_method,
            "change": Decimal(fiscal_receipt.payment) - Decimal(fiscal_receipt.total),
            "branch": branch,
            "size": "A4" if is_a4 else "80mm",
            "qrpath": f"{HTML_ROOT}/{branch.name}_{fiscal_receipt.invoiceNo}.png",
            "qrurl": branch.base_url,
            "verificationCode": fiscal_receipt.md5_hash,
            "deviceID": branch.device_id,
            "globalNo": fiscal_receipt.receiptGlobalNo,
            "FiscalDay": openday.FiscalDayNo,
            })
              
            if is_a4:    
                footer_html = render_to_string("footerA4.html", {
                "qrpath": f"{HTML_ROOT}/{branch.name}_{fiscal_receipt.invoiceNo}.png",
                "qrurl": branch.base_url,
                "verificationCode": fiscal_receipt.md5_hash,
                "deviceID": branch.device_id,
                "globalNo": fiscal_receipt.receiptGlobalNo,
                "FiscalDay": openday.FiscalDayNo,
                "bank": banking_details
                })
                header_context={
                "myCompany": branch.company,
                "branch": branch,
                
                "user":user
                
                }
                if branch.logo:
                    header_context["logo"]=branch.logo.path
                
                header_html = render_to_string("headerA4.html", header_context)
                 
            else:
                footer_html=None
                header_html=None
                
            # 3️⃣ Generate PDF using save(), passing both HTMLs
            pdf_path = save(html_content=html_content, filename=f"{branch.name}_{fiscal_receipt.invoiceNo}", footer_html=footer_html,header_html=header_html)

            # 4️⃣ Save PDF path to fiscal_receipt and return as response
            if os.path.exists(pdf_path):
                fiscal_receipt.file = pdf_path
                fiscal_receipt.save()
                return FileResponse(open(pdf_path, "rb"), content_type="application/pdf")
        except Exception as e:
            print(str(e))
            logging.info(str(e))
            return JsonResponse({"error": "Failed to complete sale. Please try again."}, status=500)

    return save_and_render_receipt()

