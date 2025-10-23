from django.http import JsonResponse,HttpResponse,FileResponse
from .models import Receipt,Credit,Debit
from django.template.loader import render_to_string
from .saver import save
from django.views.decorators.csrf import csrf_exempt
import os
import logging
from .models import Branch

@csrf_exempt
def remake_invoice(request,receipt_id):
    branch=Branch.objects.get(id=request.session["branch"])
    try:
      receipt=Credit.objects.get(id=receipt_id)
    except:
      try:
          receipt=Debit.objects.get(id=receipt_id)
      except:
          receipt=Receipt.object.get(id=receipt_id)
    try:  
      context = {
              "payment": receipt.payment,
              "change": round(float(receipt.payment) - float(receipt.total), 2),
              "products": receipt.products,
              "subtotal": receipt.subtotal,
              "tax": receipt.tax,
              "invoiceNo": receipt.invoiceNo,
              "type": receipt.receipt_type,
              "total": receipt.total,
              "date": receipt.date,
              "user":request.user,
              "time": receipt.time,
              "customer": receipt.customer,
              "currencySymbol": receipt.currency.symbol,
              "payment_method": receipt.payment_method,
              "branch": receipt.branch,
              "size":"A4" if receipt.isA4 else "80mm",

          }
      if isinstance(receipt,Credit):
          context["referenceNo"]=receipt.receiptCredited.invoiceNo,
          context["reason"]=receipt.reason
      elif isinstance(receipt,Debit):
          context["referenceNo"]=receipt.receiptDebited.invoiceNo,
          context["reason"]=receipt.reason
    
      html_content = render_to_string("sale_complete.html", context)
      if receipt.isA4:    
          footer_html = render_to_string("footerA4.html", {
            
          "bank": receipt.branch.banking_details
          })
          header_context={
          "branch": receipt.branch,
          "user":request.user

          }
          if receipt.branch.logo.path:
              header_context["logo"]=receipt.branch.logo.path
          header_html = render_to_string("headerA4.html",header_context)     
      else:
          footer_html=None
          header_html=None

      pdf_path = save(html_content=html_content, filename=f"{branch.name}_{receipt.invoiceNo}", footer_html=footer_html,header_html=header_html)
      if os.path.exists(pdf_path):
          receipt.file=pdf_path
          receipt.save()
          return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')
    except Exception as e:
       print(str(e))
       logging.info(str(e))   
       return HttpResponse(status=500)
