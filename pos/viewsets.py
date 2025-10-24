from .serializers import *
from .models import *
from rest_framework import viewsets
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator
from django.core.cache import cache
from django.db.models import Sum, Q
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework import viewsets
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.db.models import F, DecimalField, Value, ExpressionWrapper
from django.forms.models import model_to_dict
import os
import barcode
from django.db.models import F
from .models import TransactionStock
from collections import defaultdict
     
from main.settings import HTML_ROOT
from barcode.writer import ImageWriter
from .saver import saveLabel
from django.template.loader import render_to_string
from django.http import FileResponse       
from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone
from django.db import transaction
from django.db.models import Prefetch
from django.http import FileResponse

from rest_framework import viewsets, status
from rest_framework.response import Response
from decimal import Decimal, ROUND_HALF_UP

@method_decorator(cache_page(60), name='list') 
class BranchViewSet(viewsets.ModelViewSet):
    queryset = Branch.objects.all()
    serializer_class = BranchSerializer

@method_decorator(cache_page(60), name='list')
class SupplierViewSet(viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer

    @action(detail=False, methods=['post'], url_path='add_individual', permission_classes=[AllowAny])
    def add_individual(self, request):
        data = request.data.copy()
        data['supplier_type'] = 'individual'

        serializer = self.get_serializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Supplier created successfully"}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    @action(detail=False, methods=['post'], url_path='add_stakeholder', permission_classes=[AllowAny])
    def add_stakeholder(self, request):
        data = request.data.copy()
        data['supplier_type'] = 'stakeholder'

        serializer = self.get_serializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Supplier created successfully"}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
@method_decorator(csrf_exempt, name='dispatch')
class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer

    @action(detail=False, methods=['post'], url_path='add_individual',permission_classes=[AllowAny])
    def add_individual(self, request):
        data = request.data.copy()
        data['customer_type'] = 'individual'

        serializer = self.get_serializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Customer created successfully"}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='add_stakeholder', permission_classes=[AllowAny])
    def add_stakeholder(self, request):
        data = request.data.copy()
        data['customer_type'] = 'stakeholder'

        serializer = self.get_serializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Customer created successfully"}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

class ProductViewSet(viewsets.ModelViewSet):
    queryset=Product.objects.all()
    serializer_class = ProductSerializer
    
    def retrieve(self, request, pk=None):
        try:
            # Try NonService first
            product = NonService.objects.get(pk=pk)
            serializer = NonServiceSerializer(product)
            return Response(serializer.data)
        except NonService.DoesNotExist:
            pass

        try:
            # Then try Service
            product = Service.objects.get(pk=pk)
            serializer = ServiceSerializer(product)
            return Response(serializer.data)
        except Service.DoesNotExist:
            return Response({"detail": "Not found."}, status=404)

    
    @method_decorator(cache_page(60), name='list')
    def list(self, request):
        #branch_id = request.session.get("branch")
        branch = Branch.objects.get(id=1)

        # Build cache key per branch
        cache_key = f"product_list"
        data = cache.get(cache_key)

        if not data:
            # NonService products
            nonservice_products = NonService.objects.annotate(
                quantity=Sum("stock__quantity", filter=Q(stock__branch=branch))
            )
            nonservice_data = NonServiceSerializer(nonservice_products, many=True).data

            # Service products
            service_products = Service.objects.all()
            service_data = ServiceSerializer(service_products, many=True).data

            # Merge and sort
            all_products = nonservice_data + service_data
            all_products.sort(key=lambda x: x["id"])

            data = all_products
            cache.set(cache_key, data, timeout=60*60)

        return Response(data)
@method_decorator(cache_page(60), name='list')
class ReceiptViewSet(viewsets.ModelViewSet):
    serializer_class = ReceiptSerializer            
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        print(self.request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        items = validated_data.pop("items", [])
        customer = validated_data.get("customer")
        currency = validated_data.get("currency")
        branch = Branch.objects.get(id=self.request.session["branch"])
        user = User.objects.last()

        # Save receipt first
        receipt = serializer.save(user=user, branch=branch)

        # Auto-generate invoiceNo using PK
        receipt.invoiceNo = f"IN{receipt.pk}"
        
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
          
        
        
        for item in items:
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
        date_str, time_str = now.split("T")
        receipt.date = date_str
        receipt.time = time_str
        customer_name = getattr(receipt.customer, "name", "Unknown Customer")
        branch_name = getattr(receipt.branch, "name", "Unknown Branch")
        currency_code = getattr(receipt.currency, "code", "Unknown")

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
        from .utils import generate_document_pdf
        return generate_document_pdf(receipt)  # Should return BytesIO
        
    def get_queryset(self):
        # Base queryset
        qs = Receipt.objects.filter(receipt_type="FISCAL TAX INVOICE")

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
class PurchaseViewSet(viewsets.ModelViewSet):
    serializer_class = PurchaseSerializer
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        items = validated_data.pop("items", [])
        supplier = validated_data.get("supplier")
        currency = validated_data.get("currency")
        branch = Branch.objects.get(id=self.request.session["branch"])
        user = User.objects.last()

        # Save purchase first
        purchase = serializer.save(user=user, branch=branch, currency=currency, supplier=supplier)
        purchase.invoiceNo = f"SP{purchase.pk}"
        

        import django.utils.timezone as timezone
        now = timezone.localtime().isoformat(timespec='seconds').split("+")[0]
        date_str, time_str = now.split("T")

        product_map = {item["product_id"]: item.get("quantity", 1) for item in items if "product_id" in item}
        special_pricing_map = {item["product_id"]: item.get("unit_price", 1) for item in items if "product_id" in item}

        non_services = NonService.objects.filter(id__in=product_map.keys()).annotate(
            quantity=Value(0),
            product_total=ExpressionWrapper(F('selling_price') * Value(0), output_field=DecimalField()),
            product_vat=ExpressionWrapper(F('vat') * Value(0), output_field=DecimalField()),
            product_subtotal=ExpressionWrapper(F('taxExclusive') * Value(0), output_field=DecimalField())
        )
        products = list(non_services)
        exc_total = Decimal("0.0000")
        tax_total = Decimal("0.0000")
        stock_entries = []

        for product in products:
            if not Decimal(special_pricing_map[product.id]) == product.selling_price:
                product.selling_price = Decimal(special_pricing_map[product.id])
                if product.tax == "15":
                    product.vat = (product.selling_price * Decimal("0.15") / Decimal("1.15")).quantize(Decimal("0.00001"), rounding=ROUND_HALF_UP)
                    product.taxExclusive = (product.selling_price / Decimal("1.15")).quantize(Decimal("0.00001"), rounding=ROUND_HALF_UP)
                else:
                    product.vat = Decimal("0.00000")
                    product.taxExclusive = product.selling_price
                if isinstance(product, NonService):
                    product.profitBT = product.selling_price - product.buying_price
                    product.profitAT = (product.profitBT - product.vat).quantize(Decimal("0.00001"), rounding=ROUND_HALF_UP)

            product.quantity = product_map.get(product.id, 0)
            product.product_total = product.selling_price * product.quantity
            product.product_vat = product.vat * product.quantity
            product.product_subtotal = product.taxExclusive * product.quantity

            exc_total += product.product_subtotal
            tax_total += product.product_vat

            stock_entry = Stock.objects.create(
                batch_no=product.stock.count() + 1 if product.stock.count() is not None else 1,
                quantity=product.quantity,
                supplier=supplier,
                buying_price=product.selling_price,
                branch=branch,
                created=now
            )
            receiptItem, created = ReceiptItem.objects.get_or_create(
                product=product,
                selling_price=product.selling_price,
                quantity=product.quantity,
                defaults={
                    "vat": product.product_vat,
                    "subtotal": product.product_subtotal,
                    "total": product.product_total,
                }
            )
            purchase.products.add(receiptItem)
            stock_entries.append(stock_entry)
            product.stock.add(stock_entry)
            product.save()

        inc_total = exc_total + tax_total
        total_15 = sum(product.selling_price * product.quantity for product in products if product.tax == "15")
        total_0 = sum(product.selling_price * product.quantity for product in products if product.tax == "0")
        total_exempt = sum(product.selling_price * product.quantity for product in products if product.tax == "Exempt")

        purchase.Total15VAT = total_15
        purchase.TotalNonVAT = total_0
        purchase.TotalExempt = total_exempt
        purchase.total = inc_total
        purchase.subtotal = exc_total
        purchase.tax = tax_total
        purchase.date = date_str
        purchase.time = time_str

        # --- Add comment for the purchase ---
        customer_name = getattr(purchase.customer, "name", "Unknown Customer")
        product_summary = ", ".join([p.product.name for p in purchase.products.all()])
        payment_method = getattr(purchase, "payment_method", "Unknown Method")
        currency_code = getattr(purchase.currency, "code", "Unknown Currency")
        user_name = purchase.user.username

        purchase.comment = (
            f"On {date_str} at {time_str}, {customer_name} purchased {product_summary} "
            f"from the {branch.name} branch. "
            f"The purchase (Invoice No: {purchase.invoiceNo}) was processed by {user_name}. "
            f"The transaction was recorded in {currency_code} currency, with a total payment of "
            f"{getattr(purchase, 'payment', 0)} via {payment_method}. "
            f"The total tax applied was {purchase.tax}. "
            f"Of this, {purchase.Total15VAT} was taxed at 15%, {purchase.TotalNonVAT} at 0%, "
            f"and {purchase.TotalExempt} was tax-exempt. "
            f"The subtotal before tax was {purchase.subtotal}, bringing the total to {purchase.total}. "
            f"The profit before tax was {getattr(purchase, 'profitBT', 0)}, after tax was {getattr(purchase, 'profitAT', 0)}."
        )
        
        from .utils import generate_document_pdf
        return generate_document_pdf(purchase)



        # Attempt to save receipt and render

    def get_queryset(self):
        # Base queryset
        qs = Purchase.objects.all()

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
class ReturnViewSet(viewsets.ModelViewSet):
    queryset = Return.objects.all()
    serializer_class = ReturnSerializer
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        # Get original purchase
        original_purchase_id = request.data.get("purchase_id")
        reason = request.data.get("reason", "No reason provided")

        try:
            purchase = Purchase.objects.get(id=original_purchase_id)
        except Purchase.DoesNotExist:
            return Response({"error": "Purchase not found"}, status=status.HTTP_404_NOT_FOUND)
        import django.utils.timezone as timezone
        now = timezone.localtime()
        date_str, time_str = now.date(), now.time().strftime("%H:%M:%S")

        # Convert original purchase to dict, excluding fields that need overriding
        purchase_dict = model_to_dict(
            purchase,
            exclude=["id", "invoiceNo", "receipt_type", "transaction_ptr", "products"]
        )

        # Mark original purchase as returned
        purchase.returned = True
        purchase.save()

        # Override for Return
        purchase_dict.update({
            "invoiceNo": f"RT{purchase.invoiceNo.replace('SP','')}",
            "receipt_type": "STOCK RETURN",
            "original_purchase": purchase,
            "reason": reason,
            "comment": reason,  # Temporary; will update with detailed comment
            "date": date_str,
            "time": time_str,
            "currency": purchase.currency,
            "user": request.user or User.objects.last(),
            "branch": purchase.branch,
        })

        # Create Return instance
        return_instance = Return.objects.create(**purchase_dict)

        # Remove stock added by this purchase
        for item in purchase.products.all():
            for stock_entry in item.product.stock.filter(purchase=purchase):
                stock_entry.delete()

        # Copy products for document reference
        return_instance.products.set(purchase.products.all())

        # Generate detailed comment
        product_summary = ", ".join([f"{item.quantity} x {item.product.name}" for item in purchase.products.all()])
        customer_name = getattr(purchase, "supplier", "Unknown Supplier")
        branch_name = getattr(purchase.branch, "name", "Unknown Branch")
        currency_code = getattr(purchase.currency, "code", "Unknown")
        payment_method = getattr(purchase, "payment_method", "Unknown")

        detailed_comment = (
            f"On {date_str} at {time_str}, {customer_name} returned products: {product_summary} "
            f"at {branch_name} branch. "
            f"The return document (Invoice No: {return_instance.invoiceNo}) was processed by {request.user}. "
            f"The transaction was recorded in {currency_code} currency. "
            f"Reason: '{reason}'. "
            f"Total payment adjustment: {getattr(purchase, 'total', 0)}. "
            f"Original totals before return - Tax: {getattr(purchase, 'tax', 0)}, "
            f"Subtotal: {getattr(purchase, 'subtotal', 0)}, Total: {getattr(purchase, 'total', 0)}."
        )

        return_instance.comment = detailed_comment
        return_instance.save()
        from .utils import generate_document_pdf
        return generate_document_pdf(return_instance)
        
@method_decorator(cache_page(60), name='list')
class QuotationViewSet(viewsets.ModelViewSet):
    serializer_class = QuotationSerializer
    queryset = Quotation.objects.all()
    
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        items = validated_data.pop("items", [])
        customer = validated_data.get("customer")
        currency = validated_data.get("currency")
        branch = Branch.objects.get(id=self.request.session["branch"])
        user = User.objects.last()

        # Save quotation first
        quotation = serializer.save(user=user, branch=branch)

        # Auto-generate invoiceNo using PK
        quotation.invoiceNo = f"QT{quotation.pk}"
       
        # Process items
        exc_total = Decimal("0.0000")
        tax_total = Decimal("0.0000")
        products = []

        # Fetch products and calculate totals
        product_ids = [item["product_id"] for item in items]
        non_services = NonService.objects.filter(id__in=product_ids)
        services = Service.objects.filter(id__in=product_ids)

        product_map = {p.id: p for p in list(non_services) + list(services)}

        for item in items:
            product = product_map.get(item["product_id"])
            if not product:
                continue

            qty = Decimal(item.get("quantity", 1))
            sp = Decimal(item.get("selling_price", product.selling_price))

            # Update price if custom
            product.selling_price = sp
            if product.tax == "15":
                product.vat = (sp * Decimal("0.15") / Decimal("1.15")).quantize(
                    Decimal("0.00001"), rounding=ROUND_HALF_UP
                )
                product.taxExclusive = (sp / Decimal("1.15")).quantize(
                    Decimal("0.00001"), rounding=ROUND_HALF_UP
                )
            else:
                product.vat = Decimal("0.00000")
                product.taxExclusive = sp

            product.quantity = qty
            product.product_total = sp * qty
            product.product_vat = product.vat * qty
            product.product_subtotal = product.taxExclusive * qty

            exc_total += product.product_subtotal
            tax_total += product.product_vat
            receiptItem, created  =ReceiptItem.objects.get_or_create(
                product=product,
                selling_price=sp,
                quantity= product.quantity,
                defaults={
                    "vat": product.product_vat,
                    "subtotal": product.product_subtotal,
                    "total": product.product_total,
                }  
            )
            
            quotation.products.add(receiptItem)

        inc_total = exc_total + tax_total
        total_15 = sum(product.selling_price * product.quantity for product in products if product.tax == "15")
        total_0 = sum(product.selling_price * product.quantity for product in products if product.tax == "0")
        total_exempt = sum(product.selling_price * product.quantity for product in products if product.tax == "Exempt")
        # Timestamp
        import django.utils.timezone as timezone
        now = timezone.localtime().isoformat(timespec='seconds').split("+")[0]
        date_str, time_str = now.split("T")
        # Save totals on quotation
        quotation.subtotal = exc_total
        quotation.tax = tax_total
        quotation.total = inc_total
        quotation.Total15VAT = total_15
        quotation.TotalNonVAT = total_0
        quotation.TotalExempt = total_exempt
        quotation.date = date_str
        quotation.time = time_str
        quotation.comment = (
            f"On {date_str} at {time_str}, {customer.name if customer else 'Unknown Customer'} requested a quotation "
            f"for {', '.join([f'{item.quantity} x {item.product.name}' for item in quotation.products.all()])} "
            f"from the {branch.name} branch. "
            f"The quotation (Invoice No: {quotation.invoiceNo}) was prepared by {user.username}. "
            f"The quotation values are in {currency.code if currency else 'Unknown Currency'}, "
            f"with a subtotal of {quotation.subtotal}, total tax of {quotation.tax}, "
            f"and a total amount of {quotation.total}. "
            f"Of this, {quotation.Total15VAT} is taxed at 15%, {quotation.TotalNonVAT} at 0%, "
            f"and {quotation.TotalExempt} is tax-exempt."
        )
        
        # Optionally: generate PDF
        # You can call your `save()` function here if needed and attach to quotation.file
        # 🧾 Generate PDF after saving quotation
        from .utils import generate_document_pdf
        return generate_document_pdf(quotation)
       

    def get_queryset(self):
        qs = self.queryset

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
class CreditViewSet(viewsets.ModelViewSet):
    serializer_class = CreditSerializer
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        original_receipt_id = request.data.get("id")
        receipt = Receipt.objects.get(id=original_receipt_id)
        reason = request.data.get("reason", "")
        import django.utils.timezone as timezone
        
        now=timezone.localtime().isoformat(timespec='seconds').split("+")[0]
        date_str, time_str = now.split("T")
        # Convert original receipt to a dict
        receipt_dict = model_to_dict(
            receipt,
            exclude=["id", "invoiceNo", "receipt_type", "receiptCredited","transaction_ptr","products"]
        )
        
        receipt.credited=True
        Receipt.objects.filter(id=receipt.id).update(
            credited=True
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
            "invoiceNo": f"CR{receipt.invoiceNo.replace('IN','')}",
            "receipt_type": "CREDIT NOTE",
            "receiptCredited": receipt,
            "reason": reason,
            "comment": reason,
            "date":date_str,
            "time":time_str,
            "currency": receipt.currency,
            "user": User.objects.last(),
            "branch": receipt.branch,
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
          
        
        # Create Credit dynamically
        credit = Credit.objects.create(**receipt_dict)
        # Copy products
        
        credit.products.set(receipt.products.all())
       
        stock_increments = defaultdict(int)
        for ts in TransactionStock.objects.filter(transaction=receipt).select_related("stock"):
            stock_increments[ts.stock_id] += ts.quantity

        # Bulk update stocks
        for stock_id, qty in stock_increments.items():
            Stock.objects.filter(id=stock_id).update(quantity=F('quantity') + qty)
            # Get or create currency
        from .utils import generate_document_pdf
        return generate_document_pdf(credit)

    def get_queryset(self):
        # Base queryset
        qs = Receipt.objects.filter(receipt_type="CREDIT NOTE")

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
class DebitViewSet(viewsets.ModelViewSet):
    serializer_class = DebitSerializer
    @transaction.atomic
    def create(self, request, *args, **kwargs):
       
        original_receipt_id = request.data.get("id")
        receipt = Receipt.objects.get(id=original_receipt_id)
        reason = request.data.get("reason", "")
        import django.utils.timezone as timezone
        
        now=timezone.localtime().isoformat(timespec='seconds').split("+")[0]
        date_str, time_str = now.split("T")
        # Convert original receipt to a dict
        receipt_dict = model_to_dict(
            receipt,
            exclude=["id", "invoiceNo", "receipt_type", "receiptCredited","transaction_ptr","products"]
        )
        Receipt.objects.filter(id=receipt.id).update(
            debited=True
            )
        # Extract details for comment
        customer_name = getattr(receipt.customer, "name", "Unknown Customer")
        product_summary = ", ".join([p.product.name for p in receipt.products.all()])
        branch_name = getattr(receipt.branch, "name", "Unknown Branch")
        currency_code = getattr(receipt.currency, "code", "Unknown Currency")
        payment_method = getattr(receipt, "payment_method", "Unknown Method")
        
        # Override only the fields specific to credit
        receipt_dict.update({
            "invoiceNo": f"DB{receipt.invoiceNo.replace('IN','')}",
            "receiptDebited": receipt,
            "reason": reason,
            "receipt_type": "DEBIT NOTE",
            "comment": reason,
            "date":date_str,
            "time":time_str,
            "currency": receipt.currency,
            "user": User.objects.last(),
            "branch": receipt.branch,
            "comment": (
            f"On {date_str} at {time_str}, {customer_name} was issued a debit note for {product_summary} "
            f"at the {branch_name} branch. "
            f"The debit note (Invoice No: {receipt.invoiceNo}) was processed by {receipt.user.username}. "
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
        # Create Credit dynamically
        debit = Debit.objects.create(**receipt_dict)
        # Copy products
        debit.products.set(receipt.products.all())
        from .utils import generate_document_pdf
        return generate_document_pdf(debit)
     
    def get_queryset(self):
        # Base queryset
        qs = Receipt.objects.filter(receipt_type="DEBIT NOTE")

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
class CurrencyViewSet(viewsets.ModelViewSet):
    queryset = Currency.objects.all()
    serializer_class = CurrencySerializer

@method_decorator(cache_page(60), name='list')
class StackHolderViewSet(viewsets.ModelViewSet):
    queryset = StackHolder.objects.all()
    serializer_class = StackHolderSerializer
    
@method_decorator(cache_page(60), name='list')
class CompanyViewSet(viewsets.ModelViewSet):
    queryset = Company.objects.all()
    serializer_class = CompanySerializer

@method_decorator(cache_page(60), name='list')
class StockViewSet(viewsets.ModelViewSet):
    queryset = Stock.objects.all()
    serializer_class = StockSerializer
@method_decorator(cache_page(60), name='list')
class PriceChangesViewSet(viewsets.ModelViewSet):
    queryset = PriceChanges.objects.all()
    serializer_class = PriceChangesSerializer
@method_decorator(cache_page(60), name='list')
class SpecialPriceSaleViewSet(viewsets.ModelViewSet):
    queryset = SpecialPriceSale.objects.all()
    serializer_class = SpecialPriceSaleSerializer
@method_decorator(cache_page(60), name='list')
class BankingDetailsViewSet(viewsets.ModelViewSet):
    queryset = BankingDetails.objects.all()
    serializer_class = BankingDetailsSerializer
    def create(self, request, *args, **kwargs):
        try:
            stackholder_id = request.data.get("stackholder")
            currency_id = request.data.get("currency")

            stackholder = StackHolder.objects.get(id=stackholder_id)
            currency = Currency.objects.get(id=currency_id)

            # Check if BankingDetails already exists for this stackholder + currency
            banking_details = BankingDetails.objects.filter(stackholder=stackholder, currency=currency).first()

            if banking_details:
                # Update existing record
                for field in ["bank", "bank_branch", "account_name", "account_number", "bank_account", "swift_code"]:
                    if field in request.data:
                        setattr(banking_details, field, request.data[field])
                banking_details.currency = currency
                banking_details.save()
                serializer = self.get_serializer(banking_details)
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                # Create new record
                data = request.data.copy()
                data["stackholder"] = stackholder.id
                data["currency"] = currency.id
                serializer = self.get_serializer(data=data)
                serializer.is_valid(raise_exception=True)
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)

        except StackHolder.DoesNotExist:
            return Response({"error": "StackHolder not found"}, status=status.HTTP_404_NOT_FOUND)
        except Currency.DoesNotExist:
            return Response({"error": "Currency not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(str(e))
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
@method_decorator(cache_page(60), name='list')
class TransactionViewSet(viewsets.ModelViewSet):
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
  
    def retrieve(self, request, pk=None):
        """
        GET /receipts/{id}/reprint_invoice/
        """
        try:
            # Get branch ID from session
            branch_id = request.session.get("branch")
            
            if not branch_id:
                receipt = super().get_queryset().filter(id=pk).first()
            else:
                branch = Branch.objects.get(id=branch_id)
                receipt = super().get_queryset().filter(id=pk, branch=branch).first()

            # Return the file
            return FileResponse(
                open(receipt.file.path, "rb"),
                content_type="application/pdf",
                as_attachment=True,
                filename=f"receipt_{pk}.pdf"
            )

        except Receipt.DoesNotExist:
            return Response({"error": "Receipt not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(str(e))
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@method_decorator(cache_page(60), name='list')
class TransactionStockViewSet(viewsets.ModelViewSet):
    queryset = TransactionStock.objects.all()
    serializer_class = TransactionStockSerializer

@method_decorator(cache_page(60), name='list')
class ServiceViewSet(viewsets.ModelViewSet):
    queryset = Service.objects.all()
    serializer_class = ServiceSerializer
    
    
@method_decorator(cache_page(60), name='list')
class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    
@method_decorator(cache_page(60), name='list')
class NonServiceViewSet(viewsets.ModelViewSet):
    queryset = NonService.objects.all()
    serializer_class = NonServiceSerializer

    @action(detail=True, methods=['get'], url_path='label')
    def print_label(self, request, pk=None):
        try:
            product = NonService.objects.get(id=pk)
            barcode_value = product.product_code

            # Generate barcode image
            CODE128 = barcode.get_barcode_class('code128')
            barcode_img = CODE128(barcode_value, writer=ImageWriter())
            barcode_path = f"{HTML_ROOT}/{product.name}"
            barcode_img.save(barcode_path)

            # Render HTML and generate PDF
            context = {"name": f"{barcode_path}.png"}
            html = render_to_string("label.html", context)
            pdf_path = saveLabel(html, f"{product.name}")

            if os.path.exists(pdf_path):
                # Use FileResponse for binary files
                return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf', as_attachment=True)
            else:
                return Response({"error": "PDF could not be generated"}, status=500)

        except NonService.DoesNotExist:
            return Response({"error": "Product not found"}, status=404)
        except Exception as e:
            print(str(e))
            return Response({"error": "Internal server error"}, status=500)    
    

class PackViewSet(viewsets.ModelViewSet):
    queryset = Pack.objects.all()
    serializer_class = PackSerializer
    @action(detail=True, methods=['post'], url_path='break')
    def break_pack(self, request, pk=None):
       
        try:
            branch_id = request.session.get("branch")
            if not branch_id:
                return Response({"error": "Branch not found in session"}, status=status.HTTP_403_FORBIDDEN)

            branch = Branch.objects.get(id=branch_id)
            packs_to_break = int(request.data.get("units", 1))

            # Get the Pack and base NonService
            pack = Pack.objects.get(id=pk)
            units_per_pack = pack.units
            base_product = pack.nonservice_reference

            # Check available pack stock
            total_pack_stock = sum([s.quantity for s in pack.stock.all()])
            if packs_to_break > total_pack_stock:
                return Response({
                    "error": f"Only {total_pack_stock} packs available to break"
                }, status=status.HTTP_400_BAD_REQUEST)

            # Deduct packs from Pack stock
            qty_left = packs_to_break
            total_pack_buying_price = Decimal(0)
            for stock_entry in pack.stock.order_by('id'):
                if qty_left <= 0:
                    break
                available = stock_entry.quantity
                if available <= 0:
                    continue
                deduct = min(available, qty_left)
                stock_entry.quantity -= deduct
                stock_entry.save()
                total_pack_buying_price += Decimal(deduct) * stock_entry.buying_price
                qty_left -= deduct

            # Create new NonService stock entry for the returned units
            total_units_returned = units_per_pack * packs_to_break
            buying_price_per_unit = (total_pack_buying_price / total_units_returned).quantize(
                Decimal("0.00001"), rounding=ROUND_HALF_UP
            )

            stock = Stock.objects.create(
                batch_no=1,
                quantity=total_units_returned,
                buying_price=buying_price_per_unit,
                branch=branch,
                created=datetime.datetime.now(),
                expired=False,
            )
            base_product.stock.add(stock)

            return Response({
                "message": f"{packs_to_break} pack(s) broken successfully",
                "total_units_returned": total_units_returned,
                "pack_id": pack.id
            }, status=status.HTTP_200_OK)

        except Pack.DoesNotExist:
            return Response({"error": "Pack not found"}, status=status.HTTP_404_NOT_FOUND)
        except Branch.DoesNotExist:
            return Response({"error": "Branch not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print("Error:", str(e))
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    

@method_decorator(cache_page(60), name='list')
class PromotionViewSet(viewsets.ModelViewSet):
    queryset = Promotion.objects.all()
    serializer_class = PromotionSerializer
@method_decorator(cache_page(60), name='list')
class ReportEntryViewSet(viewsets.ModelViewSet):
    queryset = ReportEntry.objects.all()
    serializer_class = ReportEntrySerializer
@method_decorator(cache_page(60), name='list')
class IngredientViewSet(viewsets.ModelViewSet):
    queryset = Ingredient.objects.all()
    serializer_class = IngredientSerializer
@method_decorator(cache_page(60), name='list')
class RecipeViewSet(viewsets.ModelViewSet):
    queryset = Recipe.objects.all()
    serializer_class = RecipeSerializer
    def perform_create(self, serializer):
        
        data = serializer.validated_data

        # Extract items and units
        item_ids = data.pop("items", [])
        units_list = data.pop("units", [])

        # Save the Recipe first
        recipe = serializer.save()

        # Fetch NonService products
        products = NonService.objects.filter(id__in=item_ids)

        # Create Ingredient instances
        ingredients = []
        for i, product in enumerate(products):
            unit_amount = units_list[i] if i < len(units_list) else None
            ingredient, created = Ingredient.objects.get_or_create(
                product=product,
                recipe=recipe,
                defaults={"unit": unit_amount}
            )
            ingredients.append(ingredient)

        # Link ingredients to recipe
        recipe.ingredients.set(ingredients)
    
    @action(detail=True, methods=['post'], url_path='assemble')
    def assemble(self, request, pk=None):
        try:
            recipe = self.get_object()  # get the Recipe instance
            branch = Branch.objects.get(id=request.session.get("branch"))

            units = Decimal(request.data.get("units", "0"))
            if units <= 0:
                return Response({"error": "Units must be greater than 0"}, status=status.HTTP_400_BAD_REQUEST)

            # Ensure recipe has ingredients
            ingredients = recipe.ingredients.all()
            if not ingredients:
                return Response({"error": "Recipe has no ingredients"}, status=status.HTTP_400_BAD_REQUEST)

            total_ingredient_cost = Decimal("0")
            stock_deductions = {}

            # Deduct ingredients from stock and calculate total cost
            for ing in ingredients:
                product = ing.product
                required_qty = Decimal(ing.unit) * units

                stocks = product.stock.all()
                qty_left = required_qty

                for s in stocks.order_by('id'):
                    if qty_left <= 0:
                        break
                    available = Decimal(s.quantity)
                    if available <= 0:
                        continue

                    deduct = min(available, qty_left)
                    total_ingredient_cost += deduct * Decimal(s.buying_price)
                    stock_deductions[s.id] = stock_deductions.get(s.id, Decimal("0")) + deduct
                    qty_left -= deduct

                if qty_left > 0:
                    return Response({"error": f"Not enough stock for ingredient {product.name}"},
                                    status=status.HTTP_400_BAD_REQUEST)

            # Multiply by recipe unit ratio if needed
            recipe_unit_ratio = getattr(recipe, "unit", Decimal("1"))
            total_buying_price = (total_ingredient_cost * recipe_unit_ratio).quantize(Decimal("0.00001"), rounding=ROUND_HALF_UP)

            # Create stock entry for the assembled recipe
            last_batch_no = recipe.stock.all().last().batch_no if recipe.stock.exists() else 0
            recipe.stock.create(
                batch_no=last_batch_no + 1,
                quantity=units,
                branch=branch,
                buying_price=total_buying_price,
                created=datetime.datetime.now()
            )

            # Deduct ingredient stock quantities
            for stock_id, deducted in stock_deductions.items():
                s = Stock.objects.get(id=stock_id)
                s.quantity -= deducted
                s.save()

            return Response({
                "message": "Recipe assembled successfully",
                "total_buying_price": str(total_buying_price),
                "unit_ratio": str(recipe_unit_ratio)
            }, status=status.HTTP_200_OK)

        except Branch.DoesNotExist:
            return Response({"error": "Branch not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print("Error assembling recipe:", e)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
from decimal import Decimal, ROUND_HALF_UP
import json
import os
from io import BytesIO


class StockTransferViewSet(viewsets.ModelViewSet):
    queryset = StockTransfer.objects.all()
    serializer_class = StockTransferSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        items = validated.pop("items", [])  # expected list of dicts with product_id, quantity, selling_price, product_name...
        to_branch = validated.get("destination") or validated.get("to_branch")  # adapt to your serializer field name
        user = request.user
        from_branch_id = request.session.get("branch")
        if not from_branch_id:
            return Response({"error": "Source branch not in session"}, status=status.HTTP_400_BAD_REQUEST)

        from_branch = Branch.objects.filter(id=from_branch_id).first()
        if not from_branch or not to_branch:
            return Response({"error": "Branch not found"}, status=status.HTTP_404_NOT_FOUND)

        if not items:
            return Response({"error": "No items to transfer"}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.localtime()
        now_iso = now.isoformat(timespec="seconds")
        date_str, time_str = now_iso.split("T")

        # Build product map and load product objects
        product_ids = [int(i["product_id"]) for i in items if "product_id" in i]
        non_services = list(NonService.objects.filter(id__in=product_ids))
        services = list(Service.objects.filter(id__in=product_ids))
        product_map = {p.id: p for p in (non_services + services)}

        # Prefetch source stocks for relevant non-services (branch-limited)
        stock_qs = Stock.objects.filter(branch=from_branch, quantity__gt=0).order_by("id")
        non_services_prefetched = list(
            NonService.objects.filter(id__in=[ns.id for ns in non_services])
            .prefetch_related(Prefetch("stock", queryset=stock_qs, to_attr="prefetched_stock"))
        )

        # Flatten stock entries and dedupe
        all_stock_entries = []
        for ns in non_services_prefetched:
            all_stock_entries.extend(getattr(ns, "prefetched_stock", []))
        stock_map_by_id = {s.id: s for s in all_stock_entries}
        all_stock_entries = list(stock_map_by_id.values())
        stock_ids = list(stock_map_by_id.keys())

        # Lock stock rows for update
        locked_stock_map = {}
        if stock_ids:
            locked = list(Stock.objects.select_for_update().filter(id__in=stock_ids))
            locked_stock_map = {s.id: s for s in locked}

        # available quantities
        stock_available = {sid: Decimal(str(locked_stock_map[sid].quantity)) for sid in locked_stock_map}

        # trackers
        stock_deductions = {}     # stock_id -> Decimal deducted
        updated_stocks = []       # source stocks to bulk_update
        stocks_to_create = []     # new Stock objects for destination
        used_stock_entries = []   # (source_stock_instance, Decimal deducted)

        # totals and product list for PDF/comment
        exc_total = Decimal("0.00000")
        tax_total = Decimal("0.00000")
        products_for_totals = []
        product_lines_for_comment = []
        receipt_items_created = []

        # First pass: compute VAT/subtotals/totals and plan stock deductions
        for item in items:
            pid = int(item.get("product_id"))
            qty = Decimal(str(item.get("quantity", 1)))
            product = product_map.get(pid)
            if not product:
                # skip unknown product
                continue

            # selling price: prefer provided else product.selling_price
            sp = Decimal(str(item.get("selling_price", getattr(product, "selling_price", "0"))))
            product.selling_price = sp

            # VAT logic (matches your second snippet)
            tax_field = getattr(product, "tax", "Exempt")
            if str(tax_field) == "15":
                product.vat = (sp * Decimal("0.15") / Decimal("1.15")).quantize(MONEY_PREC, rounding=ROUNDING)
                product.taxExclusive = (sp / Decimal("1.15")).quantize(MONEY_PREC, rounding=ROUNDING)
            elif str(tax_field) == "0":
                product.vat = Decimal("0.00000")
                product.taxExclusive = sp
            else:
                product.vat = Decimal("0.00000")
                product.taxExclusive = sp

            product.quantity = qty
            product.product_total = (sp * qty).quantize(MONEY_PREC, rounding=ROUNDING)
            product.product_vat = (product.vat * qty).quantize(MONEY_PREC, rounding=ROUNDING)
            product.product_subtotal = (product.taxExclusive * qty).quantize(MONEY_PREC, rounding=ROUNDING)

            exc_total += product.product_subtotal
            tax_total += product.product_vat
            products_for_totals.append(product)

            pname = item.get("product_name", getattr(product, "name", f"Product {pid}"))
            product_lines_for_comment.append(f"{qty} × {pname} at {sp} each")

            # Plan stock deductions if NonService
            if isinstance(product, NonService):
                qty_left = qty
                prefetched = getattr(product, "prefetched_stock", None)
                if prefetched is None:
                    # fallback: match via product FK on Stock if your model uses 'nonservice' or 'product'
                    prefetched = [s for s in all_stock_entries if getattr(s, "nonservice_id", None) == product.id or getattr(s, "product_id", None) == product.id]

                for entry in prefetched:
                    if qty_left <= 0:
                        break
                    sid = entry.id
                    available = stock_available.get(sid, Decimal(0))
                    if available <= 0:
                        continue
                    deduct = min(available, qty_left)
                    stock_available[sid] = available - deduct
                    stock_deductions[sid] = stock_deductions.get(sid, Decimal(0)) + deduct
                    qty_left -= deduct

                if qty_left > 0:
                    return Response({"error": f"Not enough stock for product id {product.id}"}, status=status.HTTP_400_BAD_REQUEST)

        # Apply deductions: update source stocks, prepare destination stocks, track used entries
        for stock_id, deducted in stock_deductions.items():
            stock = locked_stock_map.get(stock_id)
            if not stock:
                continue

            original_qty = Decimal(str(stock.quantity))
            stock.quantity = (original_qty - deducted)
            # If you track 'sold' or profit fields, update here (optional)
            # stock.sold = (getattr(stock, 'sold', Decimal(0)) or Decimal(0)) + deducted

            updated_stocks.append(stock)

            # Create new stock for destination branch (copy relevant fields)
            new_stock_kwargs = {
                "supplier": stock.supplier,
                "quantity": deducted,
                "buying_price": stock.buying_price,
                "profitBT": stock.profitBT,
                "profitAT": stock.profitAT,
                "branch": to_branch,
                "created": now_iso,
                "expiry_date": stock.expiry_date,
            }
            if hasattr(stock, "nonservice_id"):
                new_stock_kwargs["nonservice_id"] = getattr(stock, "nonservice_id")
            elif hasattr(stock, "product_id"):
                new_stock_kwargs["product_id"] = getattr(stock, "product_id")

            new_stock = Stock(**new_stock_kwargs)
            stocks_to_create.append(new_stock)
            used_stock_entries.append((stock, deducted))

        # Persist stock updates
        if updated_stocks:
            Stock.objects.bulk_update(updated_stocks, ["quantity"])
        if stocks_to_create:
            Stock.objects.bulk_create(stocks_to_create)

        # Create StockTransfer (no invoiceItems JSON — we'll use ReceiptItem rows)
        last_transfer = StockTransfer.objects.order_by("id").last()
        next_no = f"ST{last_transfer.id + 1}" if last_transfer else "ST1"
        transfer = StockTransfer.objects.create(
            destination=to_branch,
            isA4=True,
            receipt_type="STOCK Transfer",
            date=date_str,
            time=time_str,
            invoiceNo=next_no,
            branch=from_branch,
            user=user,
        )

        # Create / get ReceiptItem rows and attach to transfer
        for item in items:
            pid = int(item.get("product_id"))
            product = product_map.get(pid)
            if not product:
                continue
            qty = Decimal(str(item.get("quantity", 1)))
            sp = Decimal(str(item.get("selling_price", getattr(product, "selling_price", "0"))))

            # compute fields consistent with earlier calculations
            subtotal = (getattr(product, "taxExclusive", sp) * qty).quantize(MONEY_PREC, rounding=ROUNDING)
            total = (sp * qty).quantize(MONEY_PREC, rounding=ROUNDING)
            vat = (getattr(product, "vat", Decimal("0.00000")) * qty).quantize(MONEY_PREC, rounding=ROUNDING)

            # Create or get similar ReceiptItem (matches your earlier code)
            receipt_item, created = ReceiptItem.objects.get_or_create(
                product=product,
                selling_price=sp,
                quantity=qty,
                defaults={
                    "subtotal": subtotal,
                    "total": total,
                    "vat": vat,
                },
            )

            # If it already existed but you want to update subtotal/total/vat, you can update here:
            if not created:
                # Update fields if they differ (optional)
                changed = False
                if getattr(receipt_item, "subtotal", None) != subtotal:
                    receipt_item.subtotal = subtotal
                    changed = True
                if getattr(receipt_item, "total", None) != total:
                    receipt_item.total = total
                    changed = True
                if getattr(receipt_item, "vat", None) != vat:
                    receipt_item.vat = vat
                    changed = True
                if changed:
                    receipt_item.save(update_fields=["subtotal", "total", "vat"])

            # Attach to transfer (adjust m2m name if different)
            try:
                transfer.products.add(receipt_item)
            except Exception:
                # If StockTransfer doesn't have a M2M to ReceiptItem, ignore or adapt as needed
                pass

            receipt_items_created.append(receipt_item)

        # Totals on transfer (mirror your second snippet)
        transfer.subtotal = exc_total
        transfer.tax = tax_total
        transfer.total = exc_total + tax_total
        transfer.Total15VAT = sum((p.selling_price * p.quantity) for p in products_for_totals if getattr(p, "tax", "") == "15")
        transfer.TotalNonVAT = sum((p.selling_price * p.quantity) for p in products_for_totals if getattr(p, "tax", "") == "0")
        transfer.TotalExempt = sum((p.selling_price * p.quantity) for p in products_for_totals if getattr(p, "tax", "") not in ("15", "0"))

        # Create comment similar to your receipt snippet
        user_str = getattr(user, "username", str(user))
        branch_name = getattr(from_branch, "name", "Unknown Branch")
        customer_name = getattr(to_branch, "name", "Unknown Branch")
        currency_code = getattr(getattr(transfer, "currency", None), "code", "USD")
        product_summary = ", ".join(product_lines_for_comment) if product_lines_for_comment else "No products listed"

        comment = (
            f"On {date_str} at {time_str}, {customer_name} received {product_summary} from {branch_name}. "
            f"Invoice No: {transfer.invoiceNo}. Processed by {user_str}. Currency: {currency_code}. "
            f"Subtotal: {transfer.subtotal}, Tax: {transfer.tax}, Total: {transfer.total}."
        )
        transfer.comment = comment
        transfer.save()  # persist computed totals/comment/file if set later

        # Create TransactionStock entries linking used source stocks to this transfer
        tx_objects = [
            TransactionStock(transaction=transfer, stock=stock_entry, quantity=qty_decimal)
            for stock_entry, qty_decimal in used_stock_entries
        ]
        if tx_objects:
            TransactionStock.objects.bulk_create(tx_objects)

        # Generate PDF using your centralized generate_pdf(transfer)
        from .utils import generate_document_pdf
        return generate_document_pdf(transfer)