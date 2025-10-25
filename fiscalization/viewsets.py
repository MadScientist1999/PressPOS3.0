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
from decimal import Decimal
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
        items = validated_data.pop("items", [])
        customer = validated_data.get("customer")
        currency = validated_data.get("currency")
        branch = FiscalBranch.objects.get(id=self.request.session["branch"])
        openday = OpenDay.objects.filter(open=True, branch=branch).last()
        user = User.objects.last()
        
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
          
        for i,item in enumerate(items):
            product = product_map.get(item["product_id"])
            
            if not product:
                continue
            
            product.line_number=i
            product.production=branch.production
            product.quantity = Decimal(item.get("quantity", 1))
            product.selling_price = Decimal(item.get("selling_price", product.selling_price))

            exc_total += product.subtotal
            tax_total += product.total_vat
            products_for_totals.append(product)

            # Stock adjustment remains the same for NonService
            try:
                used_stock_entries = product.adjust_stock(stock_available, stock_by_nonservice)
            except:
                print("Service")
            # ReceiptItem creation
            receipt_item, created = ReceiptItem.objects.get_or_create(
                product=product,
                selling_price=product.selling_price,
                quantity=product.quantity,
                defaults={
                    "subtotal": product.subtotal,
                    "total": product.total,
                    "vat": product.total_vat,
                },
            )
            receipt.products.add(receipt_item)
            receipt.add_receipt_line(product.json_body)
            product_lines.append(f"{product.quantity} × {product.name} at {product.selling_price} each")
        
        # --- Construct comment ---
        product_summary = ", ".join(product_lines) if product_lines else "No products listed"
     
        
        # Totals
        receipt.subtotal = exc_total
        receipt.tax = tax_total
        receipt.total = exc_total + tax_total
        receipt.Total15VAT = sum(p.selling_price * p.quantity for p in products_for_totals if p.tax == "15")
        receipt.TotalNonVAT = sum(p.selling_price * p.quantity for p in products_for_totals if p.tax == "0")
        receipt.TotalExempt = sum(p.selling_price * p.quantity for p in products_for_totals if p.tax == "Exempt")
        receipt.branch=Branch.objects.get(id=branch.id)
        receipt.fiscal_branch=branch
        receipt.fiscal_day=openday
        receipt.make_fiscal_values()
        customer_name = getattr(receipt.customer, "name", "Unknown Customer")
        branch_name = getattr(receipt.fiscal_branch, "name", "Unknown Branch")
        currency_code = getattr(receipt.currency, "code", "Unknown")
        # Concatenate tax lines
        
        comment = (
            f"On {receipt.day} at {receipt.time}, {customer_name} bought {product_summary} to "
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
        return receipt.generate_document_pdf()  # Should return BytesIO
        
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
        
        # Convert original receipt to a dict
        openday = OpenDay.objects.filter(open=True, branch=receipt.branch).last()
        receipt_dict = model_to_dict(
            receipt,
            exclude=["id", "invoiceNo","receipt_ptr","branch", "receipt_type", "credited","transaction_ptr","products","signature","receiptGlobalNo","receiptCounter","day","submitted","verified","verified_at","errors","debited","qrcode","md5_hash","serverResponse","signature","receiptHash","receiptJsonbody","qrurl","submited","customer"]
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
            "receipt_type": "CREDIT NOTE",
            "fiscal_receipt": receipt,
            "receiptGlobalNo":receipt.fiscal_branch.globalNo,
            "receiptCounter":openday.counter,
            "reason": reason,
            "fiscal_day":openday,
            "currency": receipt.currency,
            "user": User.objects.last(),
            "fiscal_branch": receipt.fiscal_branch,
            "branch":receipt.branch,
            "customer": receipt.customer
           
        })
        print(receipt_dict)
        # Create Credit dynamically
        credit = FiscalCredit.objects.create(**receipt_dict)
        comment= (
            f"On {credit.day} at {credit.time}, {customer_name} was issued a credit note for {product_summary} "
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
        
        receiptJsonBody=json.loads(receipt.receiptJsonbody)["receipt"]
        # --- 1. Negate taxes ---
        for tax_line in receiptJsonBody["receiptTaxes"]:
            tax_line["SalesAmountwithTax"] = float(tax_line["SalesAmountwithTax"]) * -1
            tax_line["taxAmount"] = float(tax_line["taxAmount"]) * -1
        receiptJsonBody["receiptPayments"][0]["paymentAmount"]=f"{-1*float(receiptJsonBody['receiptPayments'][0]['paymentAmount'])}"    
        for receiptLine in receiptJsonBody["receiptLines"]:
          receiptLine["receiptLineTotal"]=receiptLine['receiptLineTotal']*-1
          receiptLine["receiptLinePrice"]=f"{float(receiptLine['receiptLinePrice'])*-1}"
        credit.comment=comment
        credit.receipt_taxes=receiptJsonBody["receiptTaxes"]
        credit.receipt_lines=receiptJsonBody["receiptLines"]
        credit.products.set(receipt.products.all())
        
        credit.make_fiscal_values()
        
        stock_increments = defaultdict(int)
      
        for ts in TransactionStock.objects.filter(transaction=receipt).select_related("stock"):
            stock_increments[ts.stock_id] += ts.quantity

        # Bulk update stocks
        for stock_id, qty in stock_increments.items():
            Stock.objects.filter(id=stock_id).update(quantity=F('quantity') + qty)
            # Get or create currency
        
        return credit.generate_document_pdf()

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
        
        # Convert original receipt to a dict
        openday = OpenDay.objects.filter(open=True, branch=receipt.branch).last()
        receipt_dict = model_to_dict(
            receipt,
            exclude=["id", "invoiceNo","receipt_ptr","branch", "receipt_type", "credited","transaction_ptr","products","signature","receiptGlobalNo","receiptCounter","day","submitted","verified","verified_at","errors","debited","qrcode","md5_hash","serverResponse","signature","receiptHash","receiptJsonbody","qrurl","submited","customer"]
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
            "receipt_type": "DEBIT NOTE",
            "fiscal_receipt": receipt,
            "receiptGlobalNo":receipt.fiscal_branch.globalNo,
            "receiptCounter":openday.counter,
            "reason": reason,
            "fiscal_day":openday,
            "currency": receipt.currency,
            "user": User.objects.last(),
            "fiscal_branch": receipt.fiscal_branch,
            "branch":receipt.branch,
            "customer": receipt.customer
           
        })
        print(receipt_dict)
        # Create Credit dynamically
        debit = FiscalDebit.objects.create(**receipt_dict)
        comment= (
            f"On {debit.day} at {debit.time}, {customer_name} was issued a debit note for {product_summary} "
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
            f"This credit note fully references the original receipt (ID: {receipt.id})."
            )
        
        receiptJsonBody=json.loads(receipt.receiptJsonbody)["receipt"]
        # --- 1. Negate taxes ---
        debit.comment=comment
        debit.receipt_taxes=receiptJsonBody["receiptTaxes"]
        debit.receipt_lines=receiptJsonBody["receiptLines"]
        debit.products.set(receipt.products.all())
        debit.make_fiscal_values()
        
       
        return debit.generate_document_pdf()
     
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
