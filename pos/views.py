# Standard library
import os
import json
import datetime
import logging
from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone
# Django
from django.http import JsonResponse, HttpResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import F, DecimalField, Value, ExpressionWrapper
from django.template.loader import render_to_string
from django.db import transaction
import re
from .other import generate_invoice_code
import base64
from .saver import save
from rest_framework import viewsets
from .models import Branch

# Local
from .models import (
    Currency, Service, Quotation, Customer, Branch, NonService,
    Receipt, Credit, Stock, TransactionStock, BankingDetails, StackHolder,
    Debit, StockTransfer, Purchase, Supplier,Pack
)

  
@csrf_exempt
def make_transfer(request):
    try:  
        if request.method != "POST":
        
            return JsonResponse({"error": "POST required"}, status=405)
        
        from django.db.models import Prefetch
        
        data = json.loads(request.body.decode("utf-8"))


        
        # Extract
        
        items = data.get("items", [])
        
        to_branch_id=data.get("to_branch_id")
        print(data)
        user = request.user
        
        branch_id = request.session.get("branch")


        
        branch = Branch.objects.filter(id=branch_id).first()


        
        to_branch = Branch.objects.filter(id=to_branch_id).first()


        
        now = datetime.datetime.now().isoformat(sep="T", timespec="seconds")
        
        date_str, time_str = now.split("T")


        
        product_map = {i["product_id"]: Decimal(str(i.get("quantity", 1))) for i in items if "product_id" in i}


        
        product_ids = list(product_map.keys())


        
        # Fetch products in one go
        
        non_services_qs = NonService.objects.filter(id__in=product_ids)
    

        
        non_services = list(non_services_qs)


        
        products = non_services


        
        # Prefetch stock only for relevant NonService objects,
        
        # and limit stocks to the current branch and positive quantity to reduce data pulled.
        
        stock_qs = Stock.objects.filter(branch=branch, quantity__gt=0).order_by("id")
        
        non_services = list(
        
            NonService.objects.filter(id__in=[ns.id for ns in non_services]).prefetch_related(
        
                Prefetch("stock", queryset=stock_qs, to_attr="prefetched_stock")
        
            )
        
        )


        
        # Build stock_by_nonservice: product_id -> list of Stock objects (limited to branch & qty>0)
        
        stock_by_nonservice = {}
        
        all_stock_entries = []  # to keep a list of all stock objects we fetched (for updating later)
        
        for ns in non_services:
        
            stocks = getattr(ns, "prefetched_stock", [])
        
            stock_by_nonservice[ns.id] = stocks
        
            all_stock_entries.extend(stocks)


        
        # Dedup all_stock_entries (because same stock may be prefetched for multiple products)
        
        stock_map = {s.id: s for s in all_stock_entries}
        
        all_stock_entries = list(stock_map.values())


        
        # Track available quantity per stock id (use Decimal)
        
        stock_available = {s.id: Decimal(str(s.quantity)) for s in all_stock_entries}


        
        # Track how much we will deduct from each stock (stock_id -> Decimal)
        
        stock_deductions = {}
        
        stocks_to_create=[]
        
        updated_stocks = []
        
        used_stock_entries = []  # list of tuples (Stock instance, Decimal deducted)
        
        receipt_lines=[]
        MONEY_PREC = Decimal("0.00001")
        ROUND = ROUND_HALF_UP

        # Process products (non_services already prefetch-handled; packs/services below)
        
        for i, product in enumerate(products):


            
            qty = Decimal(product_map.get(product.id, Decimal(0)))
            product.quantity = qty
            # VAT and Tax-exclusive calculations
            if product.tax == "Exempt":
              product.vat = Decimal("0.00000")
              product.taxExclusive = product.selling_price
            else:
              rate = Decimal(product.tax)
              product.vat = (product.selling_price * rate / (rate + 100)).quantize(MONEY_PREC, ROUND)
              product.taxExclusive = (product.selling_price / (1 + rate / 100)).quantize(MONEY_PREC, ROUND)

            # Handle stock reduction
        
            stocks = stock_by_nonservice.get(product.id, [])
        
            qty_left = Decimal(qty)


        
            for entry in stocks:
        
                    if qty_left <= 0:
        
                        break


        
                    available = stock_available.get(entry.id, Decimal(0))
        
                    if available <= 0:
        
                        continue


        
                    deduct = min(available, qty_left)
        
                    # update trackers
        
                    stock_available[entry.id] = available - deduct
        
                    stock_deductions[entry.id] = stock_deductions.get(entry.id, Decimal(0)) + deduct


        
                    qty_left -= deduct


        

        
        # Apply the stock_deductions to actual Stock instances and prepare updated_stocks + used_stock_entries
        
        for stock_id, deducted in stock_deductions.items():
        
            stock = stock_map.get(stock_id)
        
            if not stock:
        
                continue
        
            # Subtract deducted amount from stock.quantity (Decimal arithmetic)


        
            stock.quantity = (Decimal(str(stock.quantity)) - deducted)
        
            added=Stock(
        
                supplier=stock.supplier,
        
                quantity=deducted,
        
                buying_price=stock.buying_price,
        
                profitBT=stock.profitBT,
        
                profitAT=stock.profitAT,
        
                branch=to_branch,
        
                created=now,
        
                expiry_date=stock.expiry_date
        
                )


        
            stocks_to_create.append(added)
        
            updated_stocks.append(stock)
        
            used_stock_entries.append((stock, deducted))
        Stock.objects.bulk_update(updated_stocks, ["quantity", "sold", "profitBT", "profitAT"])
        
        Stock.objects.bulk_create(stocks_to_create)
        last_transfer=StockTransfer.objects.last()
        transfer=StockTransfer.objects.create(
            destination=to_branch,
            isA4=True,
            receipt_type="STOCK Transfer",
            
            date=date_str,
            time=time_str,
            invoiceNo = f"ST{last_transfer.id+1}" if last_transfer else f"ST1",
            invoiceItems=json.dumps({"invoiceItems": items}),
            branch=branch,
            user=user, 
            
            
            
        )  
        
        
 
        banking_details=None
        context = {
            "payment": 0,
            "username": user.username,
            "change": 0,
            "products": products,

            "subtotal": 0,
            "tax": 0,
            "invoiceNo": transfer.invoiceNo,
            "type": "STOCK Tranfer",
            "total": 0,
            "date": date_str,
            "time": time_str,
            "customer": to_branch,
            "currencySymbol": "USD",
            "payment_method": "Cash",
            "branch": branch,
            "size":"A4"
        }
       
        html_content = render_to_string("sale_complete.html", context)
           
        footer_html = render_to_string("footerA4.html", {
                
                "bank": banking_details
                })
        header_context={
                "branch": branch,
                "user":transfer.user
                
                }
        if branch.logo:
                    header_context["logo"]=branch.logo.path
        header_html = render_to_string("headerA4.html",header_context)
                 
                
        # 3️⃣ Generate PDF using save(), passing both HTMLs
        pdf_path = save(html_content=html_content, filename=f"{branch.name}_{transfer.invoiceNo}", footer_html=footer_html,header_html=header_html)
        
        if os.path.exists(pdf_path):
            transfer.file=pdf_path
            transfer.save()
            return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')  
        
        return JsonResponse({"success":f"Transferred to {to_branch.name}"})

    except Branch.DoesNotExist as e:
        print(str(e))
        return JsonResponse({"error": "Branch not found"}, status=404)
    except NonService.DoesNotExist as e:
        print(str(e))
        return JsonResponse({"error": "Product not found"}, status=404)
    except Exception as e:
        print(str(e))
        return JsonResponse({"error": str(e)}, status=500)


