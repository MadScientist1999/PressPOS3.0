from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse,JsonResponse
from .models import FiscalReceipt
from .signals import *
import json

@csrf_exempt
def remake_fiscal_invoice(request, receipt_id):
    if request.method != "POST":
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    # 1️⃣ Fetch the receipt
    try:
        receipt = FiscalReceipt.objects.get(id=receipt_id)
    except FiscalReceipt.DoesNotExist:
        return JsonResponse({"error": "Receipt not found"}, status=404)

    # 2️⃣ Parse incoming data
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    # 3️⃣ Update the model fields
    fields_to_update = [
        "total", "tax", "subtotal", "payment", 
        "payment_method", "Total15VAT", "TotalNonVAT", "TotalExempt", 
        "isA4",
    ]
    for field in fields_to_update:
        if field in data:
            setattr(receipt, field, data[field])
    
    receipt.invoiceNo=receipt.invoiceNo.replace("FI","FIR")
    receipt.submited=False
    
    receipt.save()  # Save updated model

    # 4️⃣ Update the receiptJsonbody to match updated model fields
    try:
        receipt_json = json.loads(receipt.receiptJsonbody)["receipt"]
    except Exception:
        return JsonResponse({"error": "Invalid receipt JSON"}, status=500)

    # Update JSON fields from the updated model
    receipt_json["receiptTotal"] = float(receipt.total)
    receipt_json["invoiceNo"] = receipt.invoiceNo
    receipt_json["receiptPayments"] = [
        {
            "moneyTypeCode": receipt.payment_method,
            "paymentAmount": float(receipt.payment)
        }
    ]
    receipt_json["receiptPrintForm"]="InvoiceA4" if receipt.isA4 else "Receipt48"
    # Dynamically build receiptTaxes based on model values
    taxes = []
    if receipt.Total15VAT > 0:
        taxes.append({
            "taxID": "3",
            "taxCode": "C",
            "taxPercent": 15.0,
            "taxAmount": round(float(receipt.tax), 2),
            "SalesAmountwithTax": float(receipt.Total15VAT)
        })
    if receipt.TotalNonVAT > 0:
        taxes.append({
            "taxID": "2",
            "taxCode": "B",
            "taxPercent": 0.0,
            "taxAmount": 0.0,
            "SalesAmountwithTax": float(receipt.TotalNonVAT)
        })
    if receipt.TotalExempt > 0:
        taxes.append({
            "taxID": "1",
            "taxCode": "A",
            "taxPercent": None,
            "taxAmount": 0.0,
            "SalesAmountwithTax": float(receipt.TotalExempt)
        })

    receipt_json["receiptTaxes"] = taxes
    receipt_json["subtotal"] = float(receipt.subtotal)
    receipt_json["Total15VAT"] = float(receipt.Total15VAT)
    receipt_json["TotalNonVAT"] = float(receipt.TotalNonVAT)
    receipt_json["TotalExempt"] = float(receipt.TotalExempt)

    # Save back updated JSON
    receipt.receiptJsonbody = json.dumps({"receipt": receipt_json})
    receipt.save()
    submitAll(request)

    return HttpResponse(status=200)
