from .models import *
from fiscalization.models import FiscalBranch
import datetime
import json

from decimal import Decimal, ROUND_HALF_UP

def presale_procedure(request):
    from django.db.models import Prefetch
    data = json.loads(request.body.decode("utf-8"))

    # Extract
    customer_id = data.get("customer_id")
    items = data.get("items", [])
    try:
      on_account=data.get("on_account")
    except:
      on_account=False
    currency_id = data.get("currency_id")
    payment = data.get("payment")
    print_format = data.get("print_format")
    payment_method = data.get("payment_method")
    change_given=data.get("change_given")
    user = request.user
    branch_id = request.session.get("branch")

    branch = (
    FiscalBranch.objects.filter(id=branch_id).first()
    or Branch.objects.filter(id=branch_id).first()
    )
    currency = Currency.objects.get(id=int(currency_id))
    customer = Customer.objects.get(id=int(customer_id)) if customer_id else None
    is_a4 = print_format == "A4"

    now = datetime.datetime.now().isoformat(sep="T", timespec="seconds")
    date_str, time_str = now.split("T")

    # Precompute maps
    # Use Decimal for quantities so partials work
    product_map = {i["product_id"]: Decimal(str(i.get("quantity", 1))) for i in items if "product_id" in i}
    special_map = {i["product_id"]: Decimal(str(i.get("selling_price", 1))) for i in items if "product_id" in i}

    product_ids = list(product_map.keys())

    # Fetch products in one go
    non_services_qs = NonService.objects.filter(id__in=product_ids)
   
    services = list(Service.objects.filter(id__in=product_ids))
    # We'll later combine them to 'products' in order
    non_services = list(non_services_qs)

    products = non_services + services

    MONEY_PREC = Decimal("0.00001")
    ROUND = ROUND_HALF_UP

    exc_total = Decimal("0")
    tax_total = Decimal("0")
    profit_at = Decimal("0")
    profit_bt = Decimal("0")
    receipt_lines = []

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

    updated_stocks = []
    used_stock_entries = []  # list of tuples (Stock instance, Decimal deducted)
    receipt_lines=[]
    # Process products (non_services already prefetch-handled; packs/services below)
    for i, product in enumerate(products):
        # Apply special pricing
        if (sp := special_map.get(product.id)) is not None:
            product.selling_price = sp

        # VAT calculations
        if product.tax == "Exempt":
            vat = Decimal("0")
            tax_exc = product.selling_price
        else:
            rate = Decimal(str(product.tax))
            vat = (product.selling_price * rate / (rate + 100)).quantize(MONEY_PREC, ROUND)
            tax_exc = (product.selling_price / (1 + rate / 100)).quantize(MONEY_PREC, ROUND)
            
        qty = Decimal(product_map.get(product.id, Decimal(0)))
        product.quantity = qty
        product.vat = vat
        product.taxExclusive = tax_exc

        product.product_total = (product.selling_price * qty).quantize(MONEY_PREC, ROUND)
        product.product_vat = (vat * qty).quantize(MONEY_PREC, ROUND)
        product.product_subtotal = (tax_exc * qty).quantize(MONEY_PREC, ROUND)
        # Handle stock reduction
        if isinstance(product, NonService):
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

                # compute profits using Decimal
                profit_bt += (product.selling_price - entry.buying_price) * deduct
                profit_at += (product.selling_price - entry.buying_price - vat) * deduct

        exc_total += product.product_subtotal
        tax_total += product.product_vat

        if isinstance(branch, FiscalBranch):
            receipt_lines.append(product.productJsonBody(i, branch.production))

    # Apply the stock_deductions to actual Stock instances and prepare updated_stocks + used_stock_entries
    for stock_id, deducted in stock_deductions.items():
        stock = stock_map.get(stock_id)
        if not stock:
            continue
        # Subtract deducted amount from stock.quantity (Decimal arithmetic)
        stock.quantity = (Decimal(str(stock.quantity)) - deducted)
        # sold might be an IntegerField historically; if you changed quantity to Decimal you probably want sold Decimal too.
        # Here we try to preserve type safely: if sold is an int field, cast deducted to int for increment; otherwise add Decimal.
        try:
            # if stock.sold supports Decimal addition this will work, otherwise it will convert
            stock.sold = stock.sold + (deducted)
        except Exception:
            # fallback to integer increase (floor)
            stock.sold = stock.sold + int(deducted)  
        stock.profitBT = stock.profitBT + (profit_bt * Decimal(0))  # no-op precaution (profit handled per-product earlier)
        stock.profitAT = stock.profitAT + (profit_at * Decimal(0))  # same as above
        
        updated_stocks.append(stock)
        used_stock_entries.append((stock, deducted))
        
    # Bulk update fields that actually changed
    # Make sure these field names exist and types match your model (quantity may be DecimalField now).
    Stock.objects.bulk_update(updated_stocks, ["quantity", "sold", "profitBT", "profitAT"])
    
    # finalize totals
    exc_total = exc_total.quantize(MONEY_PREC, ROUND)
    tax_total = tax_total.quantize(MONEY_PREC, ROUND)
    inc_total = exc_total + tax_total

    total_15 = sum(p.product_total for p in products if p.tax == "15")
    total_0 = sum(p.product_total for p in products if p.tax == "0")
    total_exempt = sum(p.product_total for p in products if p.tax == "Exempt")
    salesamountwithtax = total_15
        # --- Safely build the customer name ---
    if customer:
        if on_account:
         change_given=True
         customer.balance-=Decimal(inc_total) 
         customer.save()   
        else:
         customer.change+=Decimal(payment)-Decimal(inc_total)
         customer.save()
        if getattr(customer, "type", None) == "individual":
            customer_name = f"{customer.name} {getattr(customer, 'last_name', '')}".strip()
        else:
            customer_name = getattr(customer, "name", "Unknown Customer")
    else:
        customer_name = "Anonymous / Walk-in Customer"

    # --- Build product descriptions ---
    product_lines = []
    for p in products:
        pname = getattr(p, "name", str(p))
        qty = getattr(p, "quantity", 1)
        price = getattr(p, "selling_price", 0)
        product_lines.append(f"{qty} × {pname} at {price}")

    product_summary = ", ".join(product_lines) if product_lines else "No products sold"

    # --- Build readable invoice summary ---
    comment = (
    f"On {date_str} at {time_str}, {customer_name} purchased {product_summary} from "
    f"{getattr(branch, 'name', branch)} branch. The transaction was handled by {user} "
    f"The customer was given the change" if change_given else ""
    f"and payment of {payment} {getattr(currency, 'code', currency)} was made via {payment_method}. "
    f"The invoice was printed using the {print_format} format{' (A4)' if is_a4 else ''}. "
    
    f"The total tax charged was {tax_total}, with sales amounting to {salesamountwithtax} "
    f"including tax. Out of this, {total_15} was taxed at 15%, {total_0} at 0%, and "
    f"{total_exempt} was tax-exempt. The exclusive total before tax was {exc_total}, "
    f"and the inclusive total after tax was {inc_total}. "
    
    f"The estimated profit before tax was {profit_bt}, and after tax was {profit_at}. "
    f"A total of {len(used_stock_entries)} stock entries were used in this transaction."
    
    )
    print(comment)

    return {
            "comment":comment,
            "payment": payment,
            "is_a4": is_a4,
            "payment_method": payment_method,
            "now": now,
            "branch": branch,
            "date_str": date_str,
            "time_str": time_str,
            "user": user,
            "tax_total": tax_total,
            "receipt_lines": receipt_lines,
            "products": products,
            "invoice_items": items,
            "total_15": total_15,
            "total_exempt": total_exempt,
            "total_0": total_0,
            "currency": currency,
            "customer": customer,
            "salesamountwithtax": salesamountwithtax,
            "exc_total": exc_total,
            "inc_total": inc_total,
            "profit_at": profit_at,
            "profit_bt": profit_bt,
            "used_stock_entries": used_stock_entries,
            "print_format": print_format,
            "on_account":on_account,
            "change_given":change_given
        }

def precredit_procedure(request, receipt):
  try: 
    data = json.loads(request.body.decode("utf-8"))
    print(data)
    user = request.user
    reason = data.get("reason", "")

    # Load invoice items
    items = json.loads(receipt.invoiceItems).get("invoiceItems", [])

    # Maps for quantity and special prices
    product_map = {item["product_id"]: Decimal(item.get("quantity", 1)) for item in items if "product_id" in item}
    special_map = {item["product_id"]: Decimal(item.get("selling_price", 0)) for item in items if "product_id" in item}

    product_ids = list(product_map.keys())

    # Fetch products once (both NonService and Service)
    non_services = list(NonService.objects.filter(id__in=product_ids))
    services = list(Service.objects.filter(id__in=product_ids))
    products = non_services + services

    # Constants
    MONEY_PREC = Decimal("0.00001")
    ROUND = ROUND_HALF_UP

    # Totals
    exc_total = Decimal("0")
    tax_total = Decimal("0")
    stock_entries = []
    non_services_list = []

    # Fetch all related stock entries for this receipt
    receipt_stock_entries = list(
        TransactionStock.objects.filter(transaction=receipt).select_related("stock")
    )
   

    for product in products:
        product_id = product.id
        qty = product_map.get(product_id, Decimal("0"))
        special_price = special_map.get(product_id)

        # Apply special price if it differs from the product price
        if special_price is not None and special_price != product.selling_price:
            product.selling_price = special_price

        # VAT and Tax-exclusive calculations
        if product.tax == "Exempt":
            product.vat = Decimal("0.00000")
            product.taxExclusive = product.selling_price
        else:
            rate = Decimal(product.tax)
            product.vat = (product.selling_price * rate / (rate + 100)).quantize(MONEY_PREC, ROUND)
            product.taxExclusive = (product.selling_price / (1 + rate / 100)).quantize(MONEY_PREC, ROUND)

        # Calculate product totals
        product.quantity = qty
        product.product_total = (product.selling_price * qty).quantize(MONEY_PREC, ROUND)
        product.product_vat = (product.vat * qty).quantize(MONEY_PREC, ROUND)
        product.product_subtotal = (product.taxExclusive * qty).quantize(MONEY_PREC, ROUND)

        # Add to totals
        exc_total += product.product_subtotal
        tax_total += product.product_vat

        # Handle stock rollback for non-service items
        if not isinstance(product, Service):
            if isinstance(product, NonService):
                try:
                    for entry in receipt_stock_entries:
                        stock = entry.stock
                        qty_entry = Decimal(entry.quantity)

                        if not product.is_unlimited:
                            stock.profitBT -= (product.selling_price - stock.buying_price) * qty_entry
                            stock.profitAT -= (product.selling_price - stock.buying_price - product.vat) * qty_entry
                            stock.quantity += entry.quantity
                            stock.returned+=entry.quantity
                        else:
                            stock.profitBT -= (product.selling_price - stock.buying_price ) * qty_entry
                            stock.profitAT -= (product.selling_price - stock.buying_price - product.vat ) * qty_entry
                            

                        stock_entries.append(stock)

                    non_services_list.append(product)
                except Exception as e:
                    print(f"Error updating stock for {product}: {e}")

    # Bulk update stock changes in one go
    if stock_entries:
        Stock.objects.bulk_update(stock_entries, ["quantity", "sold", "profitBT", "profitAT"])

    # Timestamp
    Dtime = datetime.datetime.now().isoformat(sep="T", timespec="seconds")
    date, time = Dtime.split("T")
    if receipt.on_account:
         receipt.customer.balance+=Decimal(receipt.total) 
         receipt.customer.save()
    if not receipt.change_given:
        receipt.change_given=True
    return {
       
        "products": products,
        "Dtime": Dtime,
        "date": date,
        "time": time,
        "reason": reason,
        "user": user,
        "invoice_items": items,
    }
  except Exception as e:
      print(str(e))
def predebit_procedure(request, receipt):
    
    data = json.loads(request.body.decode("utf-8"))
    user = request.user

    # Timestamp
    Dtime = datetime.datetime.now().isoformat(sep="T", timespec="seconds")
    date, time = Dtime.split("T")

    # Parse invoice items
    items = json.loads(receipt.invoiceItems).get("invoiceItems", [])
    product_map = {item["product_id"]: Decimal(item.get("quantity", 1)) for item in items if "product_id" in item}
    special_map = {item["product_id"]: Decimal(item.get("selling_price", 1)) for item in items if "product_id" in item}
    product_ids = list(product_map.keys())

    # Fetch products once
    non_services = list(NonService.objects.filter(id__in=product_ids))
    packs = list(Pack.objects.filter(id__in=product_ids))
    services = list(Service.objects.filter(id__in=product_ids))
    products = non_services + services + packs

    MONEY_PREC = Decimal("0.00001")
    ROUND = ROUND_HALF_UP

    exc_total = Decimal("0")
    tax_total = Decimal("0")

    for product in products:
        # Apply special pricing
        sp_price = special_map.get(product.id)
        if sp_price is not None and sp_price != product.selling_price:
            product.selling_price = sp_price

        # VAT calculations
        if product.tax == "Exempt":
            product.vat = Decimal("0.00000")
            product.taxExclusive = product.selling_price
        else:
            rate = Decimal(product.tax)
            product.vat = (product.selling_price * rate / (rate + 100)).quantize(MONEY_PREC, ROUND)
            product.taxExclusive = (product.selling_price / (1 + rate / 100)).quantize(MONEY_PREC, ROUND)

        # Profit for non-services (skip Services)
        if not isinstance(product, Service):
            product.profitBT = (product.selling_price - getattr(product, 'buying_price', Decimal(0))).quantize(MONEY_PREC, ROUND)
            product.profitAT = (product.profitBT - product.vat).quantize(MONEY_PREC, ROUND)

        # Quantities and totals
        qty = product_map.get(product.id, Decimal(0))
        product.quantity = qty
        product.product_total = (product.selling_price * qty).quantize(MONEY_PREC, ROUND)
        product.product_vat = (product.vat * qty).quantize(MONEY_PREC, ROUND)
        product.product_subtotal = (product.taxExclusive * qty).quantize(MONEY_PREC, ROUND)

        exc_total += product.product_subtotal
        tax_total += product.product_vat

    exc_total = exc_total.quantize(MONEY_PREC, ROUND)
    tax_total = tax_total.quantize(MONEY_PREC, ROUND)
    inc_total = exc_total + tax_total

    return {
        "user": user,
        "products": products,
        "reason": data.get("reason"),
        "now": Dtime,
        "date": date,
        "time": time,
        "exc_total": exc_total,
        "tax_total": tax_total,
        "inc_total": inc_total,
    }
