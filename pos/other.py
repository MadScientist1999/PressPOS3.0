from django.http import JsonResponse,HttpResponse
from pos.models import Product,NonService,Branch,Stock
from django.views.decorators.csrf import csrf_exempt
from main.settings import HTML_ROOT
from django.utils import timezone
import string
import random
from .models import *
from django.core.mail import get_connection,EmailMessage
from django.http import JsonResponse
import json
from django.db.models import Prefetch
import json
from django.utils import timezone
from decimal import Decimal,ROUND_HALF_UP
from django.utils.encoding import iri_to_uri
from hashlib import md5


def generate_invoice_code():
    now=timezone.now()
    LETTERS = string.ascii_uppercase
    numeric_str = now.strftime("%Y%m%d%H%M%S")
    numeric_val = int(numeric_str)
    
    # Encode numeric_val to letters
    code = ""
    base = len(LETTERS)
    while numeric_val > 0:
        numeric_val, rem = divmod(numeric_val, base)
        code = LETTERS[rem] + code
    
    # Add 3 random letters for uniqueness
    code += ''.join(random.choice(LETTERS) for _ in range(3))
    
    return code

@csrf_exempt
def generate_unique_code(request):
        # Example: Use UUID shortened to 8 chars
        from django.utils.crypto import get_random_string
        try:
         while True:
            code = get_random_string(length=4).upper()
            if not Product.objects.filter(product_code=code).exists():
                return JsonResponse(status=200,data={"code":code},safe=False)
        except Exception as e:
            print(str(e))
            return HttpResponse(status=200)


@csrf_exempt
def send_invoice_email(request, receipt_id):
    branch=Branch.objects.get(id=request.session.get("branch"))
    receipt=Receipt.objects.get(id=receipt_id)
    try:
     recipient=receipt.customer.email
    except:
     return JsonResponse({"error": "Customer email not found"}, status=400)
    # Create email
    connection = get_connection(
        host='smtp.gmail.com',
        port=587,
        username=branch.email,
        password=branch.app_password,
        use_tls=True,
        fail_silently=False
    )
    email = EmailMessage(
        subject=branch.name + " has sent you an invoice",
        body="Please find attached your invoice.",
        from_email=branch.email,
        to=[recipient],
        connection=connection
    )
    email.attach("invoice.pdf", receipt.file.read(), "application/pdf")
    email.send()

    return JsonResponse({"status": "success"})

@csrf_exempt
def stock_take(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
        items = data.get("items", [])

        branch_id = request.session.get("branch")
        branch = Branch.objects.filter(id=branch_id).first()
        if not branch:
            return JsonResponse({"error": "Branch not found"}, status=400)

        # Build product_id -> quantity map
        product_map = {i["product_id"]: Decimal(str(i.get("quantity", 0))) for i in items if "product_id" in i}
        product_ids = list(product_map.keys())

        # Fetch relevant NonService products
        non_services_qs = NonService.objects.filter(id__in=product_ids)
        non_services = list(non_services_qs)

        # Prefetch stock for these products (only for the branch and qty>0)
        stock_qs = Stock.objects.filter(branch=branch, quantity__gt=0).order_by("id")
        non_services = list(
            NonService.objects.filter(id__in=[ns.id for ns in non_services]).prefetch_related(
                Prefetch("stock", queryset=stock_qs, to_attr="prefetched_stock")
            )
        )

        # Track stock availability
        stock_available = {}
        all_stock_entries = []
        stock_by_nonservice = {}
        for ns in non_services:
            stocks = getattr(ns, "prefetched_stock", [])
            stock_by_nonservice[ns.id] = stocks
            all_stock_entries.extend(stocks)
        stock_map = {s.id: s for s in all_stock_entries}
        stock_available = {s.id: Decimal(str(s.quantity)) for s in all_stock_entries}

        # Track deductions to apply
        stock_deductions = {}
        updated_stocks = []

        # Process each product in the request
        for product in non_services:
            qty = product_map.get(product.id, Decimal(0))

            # Positive qty => add stock
            if qty > 0:
                stock = Stock.objects.create(
                    quantity=qty,
                    buying_price=Decimal("0"),
                    branch=branch,
                    created=timezone.now(),
                )
                product.stock.add(stock)

            # Negative qty => reduce stock
            elif qty < 0:
                qty_left = -qty  # make positive
                stocks = stock_by_nonservice.get(product.id, [])
                for entry in stocks:
                    if qty_left <= 0:
                        break
                    available = stock_available.get(entry.id, Decimal(0))
                    if available <= 0:
                        continue
                    deduct = min(available, qty_left)
                    stock_available[entry.id] -= deduct
                    stock_deductions[entry.id] = stock_deductions.get(entry.id, Decimal(0)) + deduct
                    qty_left -= deduct

        # Apply deductions to actual Stock instances
        for stock_id, deducted in stock_deductions.items():
            stock = stock_map.get(stock_id)
            if stock:
                stock.quantity -= deducted
                stock.lost += deducted
                stock.profitAT -= deducted * stock.buying_price
                updated_stocks.append(stock)

        # Bulk update modified stock records
        if updated_stocks:
            Stock.objects.bulk_update(updated_stocks, ["quantity", "lost", "profitAT"])

        return HttpResponse(status=200)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
        # --- Safely build the customer name ---
