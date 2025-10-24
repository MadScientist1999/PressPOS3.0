from .serializers import *
from pos.models import *
from .models import *
from rest_framework import viewsets
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator
from django.forms.models import model_to_dict
from django.http import HttpResponse
from main.settings import HTML_ROOT   
from django.db import transaction
from django.db.models import Prefetch
from decimal import Decimal, ROUND_HALF_UP
from main.models import User
from .encryption import *
from django.db.models import F
import qrcode
import json
from django.db.models import F
from pos.models import TransactionStock
from collections import defaultdict
     
@method_decorator(cache_page(60), name='list')
class FiscalReceiptViewSet(viewsets.ModelViewSet):
    serializer_class = FiscalReceiptSerializer            
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        print(self.request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data
        mobile_methods = ["Ecocash", "OneMoney", "InnBucks", "Mukuru", "Telecash"]
        items = validated_data.pop("items", [])
        customer = validated_data.get("customer")
        currency = validated_data.get("currency")
        branch = FiscalBranch.objects.get(id=self.request.session["branch"])
        openday = OpenDay.objects.filter(open=True, branch=branch).last()
        user = User.objects.last()
        receipt_lines = []
        receiptTaxes = []
        # Save receipt first
        receipt = serializer.save(user=user, fiscal_branch=branch)
       
        # Auto-generate invoiceNo using PK
        receipt.invoiceNo = f"FI{receipt.pk}"
        
        # Process products
        product_ids = [item["product_id"] for item in items]
        non_services = list(NonService.objects.filter(id__in=product_ids))
        services = list(Service.objects.filter(id__in=product_ids))
        product_map = {p.id: p for p in non_services + services}
        used_stock_entries=[]
        # Prefetch stock for NonService items
        stock_qs = Stock.objects.filter(branch=branch, quantity__gt=0)
        non_services = list(
            NonService.objects.filter(id__in=[ns.id for ns in non_services])
            .prefetch_related(Prefetch("stock", queryset=stock_qs, to_attr="prefetched_stock"))
        )
        stock_by_nonservice = {ns.id: getattr(ns, "prefetched_stock", []) for ns in non_services}
        stock_available = {s.id: Decimal(str(s.quantity)) for ns in non_services for s in stock_by_nonservice.get(ns.id, [])}

        exc_total = Decimal("0.0000")
        tax_total = Decimal("0.0000")
        products_for_totals = []
        product_lines = []
          
        for i, item in enumerate(items):
            product = product_map.get(item["product_id"])
            if not product:
                continue
            
            
            qty = Decimal(item.get("quantity", 1))
            sp = Decimal(item.get("selling_price", product.selling_price))
            product.selling_price = sp

            # VAT calculations
            if product.tax == "15":
                product.vat = (sp * Decimal("0.15") / Decimal("1.15")).quantize(Decimal("0.00001"), rounding=ROUND_HALF_UP)
                product.taxExclusive = (sp / Decimal("1.15")).quantize(Decimal("0.00001"), rounding=ROUND_HALF_UP)
            elif product.tax == "0":
                product.vat = Decimal("0.00000")
                product.taxExclusive = sp
            else:  # Exempt
                product.vat = Decimal("0.00000")
                product.taxExclusive = sp

            product.quantity = qty
            product.product_total = sp * qty
            product.product_vat = product.vat * qty
            product.product_subtotal = product.taxExclusive * qty

            exc_total += product.product_subtotal
            tax_total += product.product_vat
            products_for_totals.append(product)

            # Adjust stock for NonService
            if isinstance(product, NonService):
                qty_left = qty
                for stock in stock_by_nonservice.get(product.id, []):
                    if qty_left <= 0:
                        break
                    available = stock_available.get(stock.id, Decimal(0))
                    if available <= 0:
                        continue
                    deduct = min(qty_left, available)
                    stock.quantity -= deduct
                    stock.sold += deduct
                    stock.save(update_fields=["quantity", "sold"])
                    stock_available[stock.id] -= deduct
                    qty_left -= deduct
                    used_stock_entries.append((stock, deduct))
                    
            # Create or update ReceiptItem
            receipt_item, created = ReceiptItem.objects.get_or_create(
                product=product,
                selling_price=sp,
                quantity= qty,
                defaults={
                   
                    "subtotal": product.product_subtotal,
                    "total": product.product_total,
                    "vat": product.product_vat,
                },
            )
            
            receipt.products.add(receipt_item)
            pname = item.get("product_name", "Unknown Product")
            product_lines.append(f"{qty} × {pname} at {sp} each")
            receipt_lines.append(product.productJsonBody(i, branch.production))
        # --- Construct comment ---
        product_summary = ", ".join(product_lines) if product_lines else "No products listed"
     
        
        # Totals
        receipt.subtotal = exc_total
        receipt.tax = tax_total
        receipt.total = exc_total + tax_total
        receipt.Total15VAT = sum(p.selling_price * p.quantity for p in products_for_totals if p.tax == "15")
        receipt.TotalNonVAT = sum(p.selling_price * p.quantity for p in products_for_totals if p.tax == "0")
        receipt.TotalExempt = sum(p.selling_price * p.quantity for p in products_for_totals if p.tax == "Exempt")

        # Timestamp
        import django.utils.timezone as timezone
        now = timezone.localtime().isoformat(timespec='seconds').split("+")[0]
        print(now)
        date_str, time_str = now.split("T")
        receipt.date = date_str
        receipt.time = time_str
        customer_name = getattr(receipt.customer, "name", "Unknown Customer")
        branch_name = getattr(receipt.fiscal_branch, "name", "Unknown Branch")
        currency_code = getattr(receipt.currency, "code", "Unknown")
        salesamountwithtax=receipt.Total15VAT
        
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
            if receipt.TotalExempt>0:
             append_tax("1", "A", None, 0, receipt.TotalExempt) 

            if receipt.TotalNonVAT>0:
             append_tax("2", "B", 0.00, 0, receipt.TotalNonVAT) 

            if receipt.Total15VAT>0:
             append_tax("3", "C", 15.00, tax_total, receipt.Total15VAT) 
        else:
            if receipt.Total15VAT>0:
             append_tax("1", "A", 15.00, tax_total, receipt.Total15VAT) 
            if receipt.TotalNonVAT>0:
             append_tax("2", "B", 0.00, 0, receipt.TotalNonVAT) 
            if receipt.TotalExempt>0:
             append_tax("3", "C", None, 0, receipt.TotalExempt) 

        # JSON body for receipt
        jsonBody = {
            "receiptLines": receipt_lines,
            "receiptType": "FISCALINVOICE",
            "receiptCurrency": currency.symbol,
            "receiptPrintForm": "InvoiceA4" if receipt.isA4 else "Receipt48",
            "receiptDate": now,
            "receiptPayments": [{"moneyTypeCode": "MobileWallet" if receipt.payment_method in mobile_methods else receipt.payment_method, "paymentAmount": round(float(receipt.payment), 2)}],
            "receiptTaxes": receiptTaxes,
            "receiptTotal": float(receipt.total),
            "receiptLinesTaxInclusive": True,
            "invoiceNo": receipt.invoiceNo
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
        total = int(float(receipt.total * Decimal(100)))
        previousReceiptHash = openday.previousReceiptHash
        globalNo = branch.globalNo
        local_date, local_time = now.split("T")
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
        result_string = f"{branch.device_id}{type}{currency.symbol}{globalNo}{now}{total}{tax_lines_concat}{previousReceiptHash if openday.counter != 1 else ''}"
        signature = sign_data(branch, result_string)
        receipt_hash_base64 = hash_data(result_string)
        md5_hash_16 = get_first16chars_of_signature(signature)[:16]
        receipt.hash = receipt_hash_base64
        receipt.signature = signature
        receipt.result_string = result_string
        receipt.fiscal_branch = branch
        receipt.day = openday
        receipt.md5_hash = md5_hash_16
        receipt.receiptGlobalNo = globalNo
        receipt.receiptCounter = openday.counter
        receipt.branch=Branch.objects.get(id=branch.id)
        receipt.receiptHash=receipt_hash_base64
        OpenDay.objects.filter(id=openday.id).update(
            counter=F("counter") + 1,
            previousReceiptHash=receipt_hash_base64
            )
        FiscalBranch.objects.filter(id=branch.id).update(
            globalNo=F("globalNo") + 1,
        )
        jsonBody["receiptDeviceSignature"] = {"signature": signature, "hash": receipt_hash_base64}
        jsonBody["receiptGlobalNo"] = receipt.receiptGlobalNo
        jsonBody["receiptCounter"] = receipt.receiptCounter
        jsonBody["invoiceNo"] = receipt.invoiceNo
        import json
        receipt.qrurl = f"https://{'fdms' if branch.production else 'fdmstest'}.zimra.co.zw/{branch.device_id.zfill(10)}{day}{month}{year}{globalNo:010}{md5_hash_16}"
        receipt.receiptJsonbody = json.dumps({"receipt": jsonBody})
        comment = (
            f"On {date_str} at {time_str}, {customer_name} bought {product_summary} to "
            f"the {branch_name} branch. "
            f"The invoice (Invoice No: {receipt.invoiceNo}) was processed by {user}. "
            f"The transaction was recorded in {currency_code} currency, with a payment adjustment of "
            f"{getattr(receipt, 'payment', 0)} made via {receipt.payment_method}. "
            f"The total tax adjustment amounted to {getattr(receipt, 'tax', 0)}. "
            f"Of this, {getattr(receipt, 'Total15VAT', 0)} was taxed at 15%, "
            f"{getattr(receipt, 'TotalNonVAT', 0)} at 0%, and {getattr(receipt, 'TotalExempt', 0)} was tax-exempt. "
            f"The subtotal before tax was {getattr(receipt, 'subtotal', 0)}, "
            f"bringing the inclusive total to {getattr(receipt, 'total', 0)}. "
            f"The profit before tax was {getattr(receipt, 'profitBT', 0)}, and after tax was {getattr(receipt, 'profitAT', 0)}."
            )
        receipt.comment = comment
        receipt.jsonBody = jsonBody
        qr = qrcode.QRCode(
          version=1,  # Controls the size (1 = smallest, 40 = largest)
          error_correction=qrcode.constants.ERROR_CORRECT_L,  # Low error correction
          box_size=4,  # Size of each QR box
          border=1,  # Border thickness
          )
        qr.add_data(receipt.qrurl)
        qr.make(fit=True)
        img = qr.make_image(fill="black", back_color="white")
        img.save(f"{HTML_ROOT}/{receipt.invoiceNo}.png")
        receipt.qrcode=f"{HTML_ROOT}/{receipt.invoiceNo}.png"
        receipt_stock_objects = [
        TransactionStock(
        transaction=receipt,
        stock=stock_entry,
        quantity=qty
        ) for stock_entry, qty in used_stock_entries
        ]

        # Bulk insert in one query
        TransactionStock.objects.bulk_create(receipt_stock_objects)
        # Generate PDF and return as FileResponse
        from pos.utils import generate_document_pdf
        return generate_document_pdf(receipt)  # Should return BytesIO
        
    def get_queryset(self):
        # Base queryset
        qs = FiscalReceipt.objects.filter(receipt_type="FISCAL TAX INVOICE")

        # Example: filter by branch (from query params)
        branch_id = self.request.session.get("branch")
        if branch_id:
            qs = qs.filter(branch_id=branch_id)

        # Example: filter by date range
        start_date = self.request.query_params.get('start')
        end_date = self.request.query_params.get('end')
        if start_date and end_date:
            qs = qs.filter(date__range=[start_date, end_date])

        # Add more filters as needed
        return qs

@method_decorator(cache_page(60), name='list')
class FiscalCreditViewSet(viewsets.ModelViewSet):
    serializer_class = FiscalCreditSerializer
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        original_receipt_id = request.data.get("id")
        receipt = FiscalReceipt.objects.get(id=original_receipt_id)
        if receipt.credited:
            return HttpResponse(status=500)
        reason = request.data.get("reason", "")
        import django.utils.timezone as timezone
        
        now=timezone.now().isoformat(timespec='seconds').split("+")[0]
        date_str, time_str = now.split("T")
        # Convert original receipt to a dict
        openday = OpenDay.objects.filter(open=True, branch=receipt.branch).last()
        receipt_dict = model_to_dict(
            receipt,
            exclude=["id", "invoiceNo","receipt_ptr","branch", "receipt_type", "credited","transaction_ptr","products","signature","receiptGlobalNo","receiptCounter","day","submitted","verified","verified_at","errors","debited","qrcode","md5_hash","serverResponse","signature","receiptHash","receiptJsonbody","qrurl"]
        )
        # Extract details for comment
        customer_name = getattr(receipt.customer, "name", "Unknown Customer")
        product_summary = ", ".join([p.product.name for p in receipt.products.all()])
        branch_name = getattr(receipt.branch, "name", "Unknown Branch")
        currency_code = getattr(receipt.currency, "code", "Unknown Currency")
        payment_method = getattr(receipt, "payment_method", "Unknown Method")
        user_name = receipt.user.username
        
        # Override only the fields specific to credit
        receipt_dict.update({
            "invoiceNo": f"FC{receipt.invoiceNo.replace('FI','')}",
            "receipt_type": "DEBIT NOTE",
            "fiscal_receipt": receipt,
            "receiptGlobalNo":receipt.fiscal_branch.globalNo,
            "receiptCounter":openday.counter,
            "reason": reason,
            "day":openday,
            "date":date_str,
            "time":time_str,
            "currency": receipt.currency,
            "user": User.objects.last(),
            "fiscal_branch": receipt.fiscal_branch,
            "branch":receipt.branch,
            "comment": (
            f"On {date_str} at {time_str}, {customer_name} was issued a credit note for {product_summary} "
            f"at the {branch_name} branch. "
            f"The credit note (Invoice No: {receipt.invoiceNo}) was processed by {user_name}. "
            f"The transaction was recorded in {currency_code} currency, with a payment adjustment of "
            f"{getattr(receipt, 'payment', 0)} applied via {payment_method}. "
            f"The total tax adjustment amounted to {getattr(receipt, 'tax', 0)}. "
            f"Of this, {getattr(receipt, 'Total15VAT', 0)} was taxed at 15%, "
            f"{getattr(receipt, 'TotalNonVAT', 0)} at 0%, and {getattr(receipt, 'TotalExempt', 0)} was tax-exempt. "
            f"The subtotal before tax was {getattr(receipt, 'subtotal', 0)}, "
            f"bringing the inclusive total to {getattr(receipt, 'total', 0)}. "
            f"The profit before tax was {getattr(receipt, 'profitBT', 0)}, and after tax was {getattr(receipt, 'profitAT', 0)}. "
            f"This credit note fully references the original receipt (ID: {receipt.id})."
            )
        })
        print(receipt_dict)
        # Create Credit dynamically
        credit = FiscalCredit.objects.create(**receipt_dict)
        
        receiptJsonBody=json.loads(receipt.receiptJsonbody)["receipt"]
        for tax_line in receiptJsonBody["receiptTaxes"]:
            tax_line["SalesAmountwithTax"]*=-1
            tax_line["taxAmount"]=float(tax_line['taxAmount'])*-1
        receiptJsonBody["receiptPayments"][0]["paymentAmount"]=f"{-1*float(receiptJsonBody['receiptPayments'][0]['paymentAmount'])}"    
        for receiptLine in receiptJsonBody["receiptLines"]:
          receiptLine["receiptLineTotal"]=receiptLine['receiptLineTotal']*-1
          receiptLine["receiptLinePrice"]=f"{float(receiptLine['receiptLinePrice'])*-1}"
        try:
          creditJson={"creditDebitNote":{"receiptGlobalNo":f"{receipt.receiptGlobalNo}","fiscalDayNo":f"{receipt.day.FiscalDayNo}","receiptID":f"{json.loads(receipt.serverResponse)['receiptID']}","deviceID":receipt.fiscal_branch.device_id},"receiptLines":receiptJsonBody["receiptLines"],"receiptTaxes":receiptJsonBody["receiptTaxes"],"receiptNotes":reason,"receiptTotal":-1*receiptJsonBody["receiptTotal"],"receiptLinesTaxInclusive":True,"invoiceNo":credit.invoiceNo,"receiptCurrency":credit.currency.symbol,"receiptPrintForm":"InvoiceA4" if receipt.isA4 else "Receipt48","receiptType":"CREDITNOTE","receiptGlobalNo":credit.receiptGlobalNo,"receiptDate":now,"receiptPayments":receiptJsonBody["receiptPayments"]}
        except Exception as e:
          print(str(e))  
        if not receipt.customer is None:
         print(receipt.customer.name)
         creditJson["buyerData"]={"VATNumber": receipt.customer.vat_number, "buyerTradeName": receipt.customer.tradename, "buyerTIN": receipt.customer.tin_number, "buyerRegisterName": receipt.customer.name,"buyerAddress":{"province":receipt.customer.province,"city":receipt.customer.city,"houseNo":receipt.customer.address,"street":receipt.customer.street},"buyerContacts":{"phoneNo":receipt.customer.phone_number,"email":receipt.customer.email}} 
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
        
        credit.result_string = f"{credit.fiscal_branch.device_id}{type}{credit.currency.symbol}{credit.receiptGlobalNo}{now}{total}{tax_lines_concat}{credit.day.previousReceiptHash}"
        credit.signature=sign_data(credit.fiscal_branch,credit.result_string)
        receipt_hash_base64=hash_data(credit.result_string)
        credit.receiptHash=receipt_hash_base64
        md5_hash=get_first16chars_of_signature(credit.signature)
        credit.md5_hash=md5_hash[:16]
        creditJson["receiptDeviceSignature"]={"signature":credit.signature,"hash":receipt_hash_base64}     
        creditJson["receiptCounter"]=credit.receiptCounter
        credit.receiptJsonbody=creditJson
        credit.products.set(receipt.products.all())
        OpenDay.objects.filter(id=openday.id).update(
            counter=F("counter") + 1,
            previousReceiptHash=receipt_hash_base64
            )
        FiscalBranch.objects.filter(id=credit.fiscal_branch.id).update(
            globalNo=F("globalNo") + 1,
        )
        
        Receipt.objects.filter(id=receipt.id).update(
            credited=True
            )
    
        year, month, day = now.split("-")
          
        
        
        # Copy products
        credit.qrurl=f"https://{'fdms' if credit.fiscal_branch.production else 'fdmstest'}.zimra.co.zw/{credit.fiscal_branch.device_id.zfill(10)}{day}{month}{year}{credit.receiptGlobalNo:010}{credit.md5_hash_16}"
        credit.products.set(receipt.products.all())
        qr = qrcode.QRCode(
          version=1,  # Controls the size (1 = smallest, 40 = largest)
          error_correction=qrcode.constants.ERROR_CORRECT_L,  # Low error correction
          box_size=4,  # Size of each QR box
          border=1,  # Border thickness
          )
        qr.add_data(credit.qrurl)
        qr.make(fit=True)
        img = qr.make_image(fill="black", back_color="white")
        img.save(f"{HTML_ROOT}/{credit.invoiceNo}.png")
        credit.qrcode=f"{HTML_ROOT}/{credit.invoiceNo}.png"
        stock_increments = defaultdict(int)
        for ts in TransactionStock.objects.filter(transaction=receipt).select_related("stock"):
            stock_increments[ts.stock_id] += ts.quantity

        # Bulk update stocks
        for stock_id, qty in stock_increments.items():
            Stock.objects.filter(id=stock_id).update(quantity=F('quantity') + qty)
            # Get or create currency
        from pos.utils import generate_document_pdf
        return generate_document_pdf(credit)

    def get_queryset(self):
        # Base queryset
        qs = FiscalReceipt.objects.filter(receipt_type="CREDIT NOTE")

        # Example: filter by branch (from query params)
        branch_id = self.request.session.get("branch")
        if branch_id:
            qs = qs.filter(branch_id=branch_id)

        # Example: filter by date range
        start_date = self.request.query_params.get('start')
        end_date = self.request.query_params.get('end')
        if start_date and end_date:
            qs = qs.filter(date__range=[start_date, end_date])

        # Add more filters as needed
        return qs
@method_decorator(cache_page(60), name='list')
class FiscalDebitViewSet(viewsets.ModelViewSet):
    serializer_class = FiscalDebitSerializer
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        original_receipt_id = request.data.get("id")
        receipt = FiscalReceipt.objects.get(id=original_receipt_id)
        if receipt.debited:
            return HttpResponse(status=500)
        reason = request.data.get("reason", "")
        import django.utils.timezone as timezone
        
        now=timezone.now().isoformat(timespec='seconds').split("+")[0]
        date_str, time_str = now.split("T")
        # Convert original receipt to a dict
        openday = OpenDay.objects.filter(open=True, branch=receipt.branch).last()
        receipt_dict = model_to_dict(
            receipt,
            exclude=["id", "invoiceNo","receipt_ptr","branch", "receipt_type", "credited","transaction_ptr","products","signature","receiptGlobalNo","receiptCounter","day","submitted","verified","verified_at","errors","debited","qrcode","md5_hash","serverResponse","signature","receiptHash","receiptJsonbody","qrurl"]
        )
        # Extract details for comment
        customer_name = getattr(receipt.customer, "name", "Unknown Customer")
        product_summary = ", ".join([p.product.name for p in receipt.products.all()])
        branch_name = getattr(receipt.branch, "name", "Unknown Branch")
        currency_code = getattr(receipt.currency, "code", "Unknown Currency")
        payment_method = getattr(receipt, "payment_method", "Unknown Method")
        user_name = receipt.user.username
        
        # Override only the fields specific to credit
        receipt_dict.update({
            "invoiceNo": f"FD{receipt.invoiceNo.replace('FI','')}",
            "receipt_type": "CREDIT NOTE",
            "fiscal_receipt": receipt,
            "receiptGlobalNo":receipt.fiscal_branch.globalNo,
            "receiptCounter":openday.counter,
            "reason": reason,
            "day":openday,
            "date":date_str,
            "time":time_str,
            "currency": receipt.currency,
            "user": User.objects.last(),
            "fiscal_branch": receipt.fiscal_branch,
            "branch":receipt.branch,
            "comment": (
            f"On {date_str} at {time_str}, {customer_name} was issued a debit note for {product_summary} "
            f"at the {branch_name} branch. "
            f"The debit note (Invoice No: {receipt.invoiceNo}) was processed by {user_name}. "
            f"The transaction was recorded in {currency_code} currency, with a payment adjustment of "
            f"{getattr(receipt, 'payment', 0)} applied via {payment_method}. "
            f"The total tax adjustment amounted to {getattr(receipt, 'tax', 0)}. "
            f"Of this, {getattr(receipt, 'Total15VAT', 0)} was taxed at 15%, "
            f"{getattr(receipt, 'TotalNonVAT', 0)} at 0%, and {getattr(receipt, 'TotalExempt', 0)} was tax-exempt. "
            f"The subtotal before tax was {getattr(receipt, 'subtotal', 0)}, "
            f"bringing the inclusive total to {getattr(receipt, 'total', 0)}. "
            f"The profit before tax was {getattr(receipt, 'profitBT', 0)}, and after tax was {getattr(receipt, 'profitAT', 0)}. "
            f"This debit note fully references the original receipt (ID: {receipt.id})."
            )
        })
        print(receipt_dict)
        # Create Credit dynamically
        debit = FiscalDebit.objects.create(**receipt_dict)
        
        receiptJsonBody=json.loads(receipt.receiptJsonbody)["receipt"]
        try:
          debitJson={"creditDebitNote":{"receiptGlobalNo":f"{receipt.receiptGlobalNo}","fiscalDayNo":f"{receipt.day.FiscalDayNo}","receiptID":f"{json.loads(receipt.serverResponse)['receiptID']}","deviceID":receipt.fiscal_branch.device_id},"receiptLines":receiptJsonBody["receiptLines"],"receiptTaxes":receiptJsonBody["receiptTaxes"],"receiptNotes":reason,"receiptTotal":receiptJsonBody["receiptTotal"],"receiptLinesTaxInclusive":True,"invoiceNo":debit.invoiceNo,"receiptCurrency":debit.currency.symbol,"receiptPrintForm":"InvoiceA4" if receipt.isA4 else "Receipt48","receiptType":"DEBITNOTE","receiptGlobalNo":debit.receiptGlobalNo,"receiptDate":now,"receiptPayments":receiptJsonBody["receiptPayments"]}
        except Exception as e:
          print(str(e))  
        if not receipt.customer is None:
         print(receipt.customer.name)
         debitJson["buyerData"]={"VATNumber": receipt.customer.vat_number, "buyerTradeName": receipt.customer.tradename, "buyerTIN": receipt.customer.tin_number, "buyerRegisterName": receipt.customer.name,"buyerAddress":{"province":receipt.customer.province,"city":receipt.customer.city,"houseNo":receipt.customer.address,"street":receipt.customer.street},"buyerContacts":{"phoneNo":receipt.customer.phone_number,"email":receipt.customer.email}} 
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
        total=int(float(receipt.total)*-100)
        
        debit.result_string = f"{debit.fiscal_branch.device_id}{type}{debit.currency.symbol}{debit.receiptGlobalNo}{now}{total}{tax_lines_concat}{debit.day.previousReceiptHash}"
        
        debit.signature=sign_data(debit.fiscal_branch,debit.result_string)
        receipt_hash_base64=hash_data(debit.result_string)
        debit.receiptHash=receipt_hash_base64
        md5_hash=get_first16chars_of_signature(debit.signature)
        debit.md5_hash=md5_hash[:16]
        debitJson["receiptDeviceSignature"]={"signature":debit.signature,"hash":receipt_hash_base64}     
        debitJson["receiptCounter"]=debit.receiptCounter
        debit.receiptJsonbody=debitJson
        debit.products.set(receipt.products.all())
        
        OpenDay.objects.filter(id=openday.id).update(
            counter=F("counter") + 1,
            previousReceiptHash=receipt_hash_base64
            )
        FiscalBranch.objects.filter(id=debit.fiscal_branch.id).update(
            globalNo=F("globalNo") + 1,
        )
        
        Receipt.objects.filter(id=receipt.id).update(
            debited=True
            )
    
        year, month, day = now.split("-")
          
        
        
        # Copy products
        debit.qrurl=f"https://{'fdms' if debit.fiscal_branch.production else 'fdmstest'}.zimra.co.zw/{debit.fiscal_branch.device_id.zfill(10)}{day}{month}{year}{debit.receiptGlobalNo:010}{debit.md5_hash_16}"
        debit.products.set(receipt.products.all())
        qr = qrcode.QRCode(
          version=1,  # Controls the size (1 = smallest, 40 = largest)
          error_correction=qrcode.constants.ERROR_CORRECT_L,  # Low error correction
          box_size=4,  # Size of each QR box
          border=1,  # Border thickness
          )
        qr.add_data(debit.qrurl)
        qr.make(fit=True)
        img = qr.make_image(fill="black", back_color="white")
        img.save(f"{HTML_ROOT}/{debit.invoiceNo}.png")
        debit.qrcode=f"{HTML_ROOT}/{debit.invoiceNo}.png"
        
        from pos.utils import generate_document_pdf
        return generate_document_pdf(debit)
     
    def get_queryset(self):
        # Base queryset
        qs = FiscalReceipt.objects.filter(receipt_type="DEBIT NOTE")

        # Example: filter by branch (from query params)
        branch_id = self.request.session.get("branch")
        if branch_id:
            qs = qs.filter(branch_id=branch_id)

        # Example: filter by date range
        start_date = self.request.query_params.get('start')
        end_date = self.request.query_params.get('end')
        if start_date and end_date:
            qs = qs.filter(date__range=[start_date, end_date])

        # Add more filters as needed
        return qs
