from django.shortcuts import render
import os
from main.models import User
from fiscalization.models import FiscalBranch,ReceiptCounters
from django.http import (
    
    FileResponse,
    JsonResponse,
)
from pos.saver import saveReport
from fiscalization.models import OpenDay,DailyReports
from django.views.decorators.csrf import csrf_exempt
from django.template.loader import render_to_string
from django.http import JsonResponse,FileResponse,HttpResponse
from django.views.decorators.csrf import csrf_exempt
from main.models import User
from django.template.loader import render_to_string
from main.settings import HTML_ROOT
from decimal import Decimal
import logging
from pos.models import Branch,Currency,Customer,Transaction, Stock,Supplier,Receipt,NonService
import json
import datetime
from django.db.models import Sum, Count, Avg, Max, Min
from django.utils import timezone
logger = logging.getLogger(__name__)

@csrf_exempt
def z_report(request, id):
    # Get branch from session
    branch_id = request.session.get("branch")
    if not branch_id:
        return JsonResponse({"error": "No branch in session"}, status=400)

    try:
        branch = FiscalBranch.objects.get(id=branch_id)
    except FiscalBranch.DoesNotExist:
        return JsonResponse({"error": "Branch not found"}, status=404)

    # Get open day and daily report
    day = OpenDay.objects.filter(id=id).first()
    if not day:
        return JsonResponse({"error": "Open day not found"}, status=404)

    daily_report = DailyReports.objects.filter(FiscalDay=day).last()
    
    receipt_counters=ReceiptCounters.objects.filter(day=day)
    if not daily_report:
        return JsonResponse({"error": "Report missing"}, status=404)

    # Helper function to sum values for a specific type/currency/tax/money type
    def get_value(report_type, currency_code, tax_percent=None, money_type=None):
        qs = daily_report.entries.filter(report_type=report_type, currency__symbol=currency_code)
        if tax_percent is not None:
            qs = qs.filter(tax_percent=tax_percent)
        if money_type is not None:
            qs = qs.filter(money_type=money_type)
        return round(sum(entry.value for entry in qs), 2)

    try:
       
        currencies = Currency.objects.all()
        #currencies = [c.symbol for c in currencies_queryset]
        tax_rates = ["15.00", "0.00", "Exempt"]
        money_types = ["Cash", "Card", "MobileWallet", "Coupon", "BankTransfer", "Other"]

        counters = []

        for currency in currencies:
            receipt_counter=receipt_counters.filter(currency=currency).order_by("id")
            net15 = get_value("SaleByTax", currency.symbol, tax_percent="15.00") - get_value("SaleTaxByTax", currency, tax_percent="15.00")
            net0 = get_value("SaleByTax", currency.symbol, tax_percent="0.00") - get_value("SaleTaxByTax", currency, tax_percent="0.00")
            netEx = get_value("SaleByTax", currency.symbol, tax_percent="Exempt") - get_value("SaleTaxByTax", currency, tax_percent="Exempt")
            totalNet = net15 + net0 + netEx

            tax = get_value("SaleTaxByTax", currency.symbol)
            gross15 = get_value("SaleByTax", currency.symbol, tax_percent="15.00")
            gross0 = get_value("SaleByTax", currency.symbol, tax_percent="0.00")
            grossEx = get_value("SaleByTax", currency.symbol, tax_percent="Exempt")
            totalGross = gross15 + gross0 + grossEx

            totalCredit = (
                get_value("CreditNoteByTax", currency.symbol, tax_percent="15.00") +
                get_value("CreditNoteByTax", currency.symbol, tax_percent="0.00") +
                get_value("CreditNoteByTax", currency.symbol, tax_percent="Exempt")
            )

            totalDocument = totalGross + totalCredit

            # Calculate balances by money type
            balances = {}
            for money_type in money_types:
                balances[money_type] = get_value("BalanceByMoneyType", currency.symbol, money_type=money_type)
            try:
                no_of_receipts=receipt_counter.filter(type="FiscalReceipt").last().value
            except:
                no_of_receipts=0
            try:
             no_of_credits=receipt_counter.filter(type="CreditNote").last().value
            except:
             no_of_credits=0
            try:
             no_of_debits=receipt_counter.filter(type="DebitNote").last().value
            except:
             no_of_debits=0
            total=no_of_receipts+no_of_credits+no_of_debits
            
            if not total==0:
             counters.append({
                "currency": currency,
                "net15": net15,
                "net0": net0,
                "netEx": netEx,
                "totalNet": totalNet,
                "Tax": tax,
                "totalTax": tax,
                "gross15": gross15,
                "gross0": gross0,
                "grossEx": grossEx,
                "grossTotal": totalGross,
                "creditTotal": totalCredit,
                "total_amount": totalDocument,
                "balances": balances,
                "no_of_receipts":no_of_receipts,
                "no_of_credits": no_of_credits,
                "no_of_debits":no_of_debits,
                "total_documents": no_of_receipts+no_of_credits+no_of_debits})

        context = {
            "company": branch.company,
            "is_open": day.open,
            "fiscal": {
                "device_serial": branch.serial,
                "device_id": branch.device_id
            },
            "day": {
                "day_no": day.FiscalDayNo,
                "opened": day.FiscalDayOpened,
                "closed": day.FiscalDayClosed,
            },
            "counters": counters
        }

        # Render HTML and save PDF
        html = render_to_string("zreport.html", context)
        pdf_path = saveReport(html, f"{branch.name}_ZR{day.FiscalDayNo}")

        if os.path.exists(pdf_path):
            return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')
        else:
            logger.error(f"PDF not found at {pdf_path}")
            return JsonResponse({"error": "PDF generation failed"}, status=500)

    except Exception as e:
        print(str(e))
        logger.exception("Error generating Z report")
        return JsonResponse({"error": str(e)}, status=500)

@csrf_exempt
def customer_report(request, customer_id):
    branch = Branch.objects.get(id=request.session["branch"])
    data = json.loads(request.body)
    start = datetime.datetime.fromisoformat(data["start"]).date()
    end = datetime.datetime.fromisoformat(data["end"]).date()
    customer = Customer.objects.get(id=customer_id)
    
    # Include all relevant receipt types
    receipt_types = [
        "FISCAL TAX INVOICE",
        "DEBIT NOTE",
        "CREDIT NOTE",
        "QUOTATION",
        
    ]
    
    currencies = Currency.objects.all()
    payment_methods = [
        'Cash', 'Ecocash','OneMoney','InnBucks','Mukuru',
        'Telecash','Card','Coupon','Swipe','BankTransfer',"Other"
    ]
    
    statsInvoice = []

    try:
        for receipt_type in receipt_types:
            receiptsFull = Receipt.objects.filter(
                date__range=[start, end],
                receipt_type=receipt_type,
                customer=customer,
                branch=branch
            )
            print(receipt_type)
            try:
             for currency in currencies:
                print(currency.symbol)
                for method in payment_methods:
                    receipts = receiptsFull.filter(currency=currency, payment_method=method)
                    
                    if receipts.exists():
                        aggregated = receipts.aggregate(
                            total_sales=Sum('total'),
                            total_tax=Sum('tax'),
                            total_subtotal=Sum('subtotal'),
                            gross_profit=Sum('profitBT'),
                            net_profit=Sum('profitAT'),
                            avg_invoice=Avg('total'),
                            total_invoices=Count('id')
                            
                            
                        )

                        aggregated["currency"] = currency
                        aggregated["method"] = method
                        aggregated["receipt_type"] = receipt_type
                        aggregated = {k: (v if v is not None else 0) for k, v in aggregated.items()}
                        statsInvoice.append(aggregated)
            
            
       
            except Exception as e:
                print(str(e))
                print("JKJK")
                continue
           
        context = {
            "statsInvoice": statsInvoice,
            "currencies": currencies,
            "payment_methods": payment_methods,
            "differentiator": "Customer",
            "user": customer.name,
            "balance":customer.balance,
            "change":customer.change,
            "start": start,
            "end": end,
            "branch": branch,
        }

        html = render_to_string("report_template.html", context)
        pdf_path = saveReport(html, f"customer_report_{branch.name}{customer.name}{start}to{end}")

        if os.path.exists(pdf_path):
            return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')
    except Exception as e:
        print(str(e))
        return HttpResponse(status=500)

@csrf_exempt
def user_report(request, user_id):
    branch = Branch.objects.get(id=request.session["branch"])
    data = json.loads(request.body)
    start = datetime.datetime.fromisoformat(data["start"]).date()
    end = datetime.datetime.fromisoformat(data["end"]).date()
    user = User.objects.get(id=user_id)
    
    # Include all relevant receipt types
    receipt_types = [
        "FISCAL TAX INVOICE",
        "DEBIT NOTE",
        "CREDIT NOTE",
        "QUOTATION"
    ]
    
    currencies = Currency.objects.all()
    payment_methods = [
        'Cash', 'Ecocash','OneMoney','InnBucks','Mukuru',
        'Telecash','Card','Coupon','Swipe','BankTransfer',"Other"
    ]
    
    statsInvoice = []

    try:
        for receipt_type in receipt_types:
            receiptsFull = Receipt.objects.filter(
                date__range=[start, end],
                receipt_type=receipt_type,
                user=user,
                branch=branch
            )

            for currency in currencies:
                for method in payment_methods:
                    receipts = receiptsFull.filter(currency=currency, payment_method=method)
                    if receipts.exists():
                        aggregated = receipts.aggregate(
                            total_sales=Sum('total'),
                            total_tax=Sum('tax'),
                            total_subtotal=Sum('subtotal'),
                            gross_profit=Sum('profitBT'),
                            net_profit=Sum('profitAT'),
                            avg_invoice=Avg('total'),
                            total_invoices=Count('id')
                        )

                        aggregated["currency"] = currency
                        aggregated["method"] = method
                        aggregated["receipt_type"] = receipt_type
                        aggregated = {k: (v if v is not None else 0) for k, v in aggregated.items()}
                        statsInvoice.append(aggregated)

        context = {
            "statsInvoice": statsInvoice,
            "currencies": currencies,
            "payment_methods": payment_methods,
            "differentiator": "User",
            "user": user.username,
            "start": start,
            "end": end,
            "branch": branch,
        }

        html = render_to_string("report_template.html", context)
        pdf_path = saveReport(html, f"user_report_{branch.name}{user.username}{start}to{end}")

        if os.path.exists(pdf_path):
            return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')
    except Exception as e:
        print(str(e))
        return HttpResponse(status=500)
@csrf_exempt
def branch_report(request, branch_id):
    branch = Branch.objects.get(id=branch_id)
    data = json.loads(request.body)
    start = datetime.datetime.fromisoformat(data["start"]).date()
    end = datetime.datetime.fromisoformat(data["end"]).date()
    
    # Include all relevant receipt types
    receipt_types = [
        "FISCAL TAX INVOICE",
        "DEBIT NOTE",
        "CREDIT NOTE",
        "QUOTATION"
    ]
    
    currencies = Currency.objects.all()
    payment_methods = [
        'Cash', 'Ecocash','OneMoney','InnBucks','Mukuru',
        'Telecash','Card','Coupon','Swipe','BankTransfer',"Other"
    ]
    
    statsInvoice = []

    try:
        for receipt_type in receipt_types:
            receiptsFull = Receipt.objects.filter(
                date__range=[start, end],
                receipt_type=receipt_type,
                branch=branch
            )

            for currency in currencies:
                for method in payment_methods:
                    receipts = receiptsFull.filter(currency=currency, payment_method=method)
                    if receipts.exists():
                        aggregated = receipts.aggregate(
                            total_sales=Sum('total'),
                            total_tax=Sum('tax'),
                            total_subtotal=Sum('subtotal'),
                            gross_profit=Sum('profitBT'),
                            net_profit=Sum('profitAT'),
                            avg_invoice=Avg('total'),
                            total_invoices=Count('id')
                        )

                        aggregated["currency"] = currency
                        aggregated["method"] = method
                        aggregated["receipt_type"] = receipt_type
                        aggregated = {k: (v if v is not None else 0) for k, v in aggregated.items()}
                        statsInvoice.append(aggregated)

        context = {
            "statsInvoice": statsInvoice,
            "currencies": currencies,
            "payment_methods": payment_methods,
            "differentiator": "Branch",
            "start": start,
            "user":branch.name,
            "end": end,
            "branch": branch,
        }

        html = render_to_string("report_template.html", context)
        pdf_path = saveReport(html, f"branch_report_{branch.name}{branch.name}{start}to{end}")

        if os.path.exists(pdf_path):
            return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')
    except Exception as e:
        print(str(e))
        return HttpResponse(status=500)

@csrf_exempt
def stock_sheet_report(request):
    try:
        branch = Branch.objects.get(id=request.session["branch"])
        products=NonService.objects.all()
        stocks = Stock.objects.filter(branch=branch)  # all stock items in the branch
        import datetime
        stock_data = []
        
        for product in products:
          for stock in product.stock.filter(branch=branch):
            age=(timezone.now()-stock.created).days,
            if stock.quantity!=0:
            
             stock_data.append({
                
                "product_name":product.name,
                "created":stock.created,
                "batch":stock.batch_no,
                "quantity": stock.quantity,
                "unit_cost": stock.buying_price,
                "total_value": stock.quantity * stock.buying_price,
                "age":age,
                "returned":stock.returned,
                "expired":stock.expired,
                "supplier":stock.supplier.name if stock.supplier else "None",
                "sold":stock.sold,
                
             })
            
        context = {
            "stock_data": stock_data,
            "branch": branch,
            "report_date": datetime.date.today(),
            "differentiator": "Stock Sheet",
        }

        html = render_to_string("stock_sheet.html", context)
        pdf_path = saveReport(html, f"stock_sheet_{branch.name}_{datetime.date.today()}")

        if os.path.exists(pdf_path):
            return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')

        return HttpResponse(status=404)

    except Exception as e:
        print(str(e))
        return HttpResponse(status=500)
@csrf_exempt
def product_report(request,product_id):
    try:
        product=Product.objects.get(id=product_id)
        import datetime 
        context = {
            "product":product,
          
           
        }

        html = render_to_string("product_report.html", context)
        pdf_path = saveReport(html, f"product_{product.name}_{datetime.date.today()}")

        if os.path.exists(pdf_path):
            return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')

        return HttpResponse(status=404)

    except Exception as e:
        print(str(e))
        return HttpResponse(status=500)

@csrf_exempt
def supplier_report(request, supplier_id):
    try:
        branch = Branch.objects.get(id=request.session["branch"])
        data = json.loads(request.body)
        start = datetime.datetime.fromisoformat(data["start"]).date()
        end = datetime.datetime.fromisoformat(data["end"]).date()
        supplier = Supplier.objects.get(id=supplier_id)
        products_for_supplier=[]
        receipt_types = ["FISCAL TAX INVOICE", "DEBIT NOTE", "CREDIT NOTE", "QUOTATION"]
        currencies = Currency.objects.all()
        payment_methods = [
            'Cash','Ecocash','OneMoney','InnBucks','Mukuru',
            'Telecash','Card','Coupon','Swipe','BankTransfer',"Other"
        ]

        statsInvoice = []

        for receipt_type in receipt_types:
            receiptsFull = Receipt.objects.filter(
                date__range=[start, end],
                receipt_type=receipt_type,
                branch=branch
            )

            for currency in currencies:
                for method in payment_methods:
                    receipts = receiptsFull.filter(currency=currency, payment_method=method)
                    receipt_total_sales = 0
                    receipt_total_tax = 0
                    receipt_total_subtotal = 0
                    receipt_gross_profit = 0
                    receipt_net_profit = 0
                    count_receipts = 0

                    for receipt in receipts:
                        # Filter products in this receipt for this supplier
                        
                        products = receipt.products.all()
                        for product in products:
                            try:
                                product=NonService.objects.get(id=product.id,stock__supplier=supplier)        
                                products_for_supplier.append(product)
                            except:
                                print("Service")
                        if products_for_supplier.__len__()>0:
                            # Proportionally allocate totals
                            total_products = receipt.products.count()
                            try:
                             proportion = products_for_supplier.__len__() / total_products
                            except:
                             proportion=0
                            receipt_total_sales += float(receipt.total) * proportion
                            receipt_total_tax += float(receipt.tax) * proportion
                            receipt_total_subtotal += float(receipt.subtotal) * proportion
                            receipt_gross_profit += float(receipt.profitBT) * proportion
                            receipt_net_profit += float(receipt.profitAT) * proportion
                            count_receipts += 1

                    if count_receipts > 0:
                        agg = {
                            "total_sales": receipt_total_sales,
                            "total_tax": receipt_total_tax,
                            "total_subtotal": receipt_total_subtotal,
                            "gross_profit": receipt_gross_profit,
                            "net_profit": receipt_net_profit,
                            "avg_invoice": receipt_total_sales / count_receipts if count_receipts else 0,
                            "total_invoices": count_receipts,
                            "currency": currency,
                            "method": method,
                            "receipt_type": receipt_type
                        }
                        statsInvoice.append(agg)

        # Summary per document type
        summary_by_type = {}
        for t in receipt_types:
            summary_by_type[t] = sum(x['total_sales'] for x in statsInvoice if x['receipt_type'] == t)

        context = {
            "statsInvoice": statsInvoice,
            "currencies": currencies,
            "payment_methods": payment_methods,
            "differentiator": "Supplier",
            "user": supplier.name,
            "start": start,
            "end": end,
            "branch": branch,
            "summary_by_type": summary_by_type
        }

        html = render_to_string("report_template.html", context)
        pdf_path = saveReport(html, f"supplier_report_{branch.name}_{supplier.name}_{start}to{end}")

        if os.path.exists(pdf_path):
            return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')

        return HttpResponse(status=404)

    except Exception as e:
        print(str(e))
        return HttpResponse(status=500)
@csrf_exempt
def cash_reconciliation_report(request):
    try:
        branch = Branch.objects.get(id=request.session["branch"])
        data = json.loads(request.body)
        start = datetime.datetime.fromisoformat(data["start"]).date()
        end = datetime.datetime.fromisoformat(data["end"]).date()

        # All receipts in the period
        receipts = Transaction.objects.filter(
            date__range=[start, end],
            branch=branch
        )

        # All stock purchases in the period
        stock_purchases = Stock.objects.filter(
            branch=branch,
            created__date__range=[start, end]
        )

        # Currencies
        currencies = Currency.objects.all()
        payment_methods = [
            'Cash','Ecocash','OneMoney','InnBucks','Mukuru',
            'Telecash','Card','Coupon','Swipe','BankTransfer',"Other"
        ]

        report_data = []

        for currency in currencies:
            for method in payment_methods:
                # Filter receipts by currency and payment method
                filtered_receipts = receipts.filter(currency=currency, payment_method=method)

                total_sales = filtered_receipts.aggregate(
                    total=Sum('total'),
                    total_payment=Sum('payment'),
                    total_tax=Sum('tax')
                )['total'] or 0

                # Filter stock purchases by currency
                filtered_purchases = stock_purchases.filter(currency=currency)
                total_purchases = sum([s.buying_price * s.quantity for s in filtered_purchases])

                # Net money we should have
                net_expected = total_sales - total_purchases

                report_data.append({
                    "currency": currency,
                    "method": method,
                    "total_sales": total_sales,
                    "total_purchases": total_purchases,
                    "net_expected": net_expected
                })

        context = {
            "report_data": report_data,
            "branch": branch,
            "start": start,
            "end": end,
            "differentiator": "Cash Reconciliation"
        }

        html = render_to_string("cash_reconciliation_template.html", context)
        pdf_path = saveReport(html, f"cash_reconciliation_{branch.name}_{start}to{end}")

        if os.path.exists(pdf_path):
            return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')

        return HttpResponse(status=404)

    except Exception as e:
        print(str(e))
        return HttpResponse(status=500)

@csrf_exempt
def sales_report(request):
    try:
        data = json.loads(request.body)
        branch = Branch.objects.get(id=request.session["branch"])
        start = datetime.datetime.fromisoformat(data["start"]).date()
        end = datetime.datetime.fromisoformat(data["end"]).date()

        currencies = Currency.objects.all()
        payment_methods = [
            'Cash', 'Ecocash','OneMoney','InnBucks','Mukuru',
            'Telecash','Card','Coupon','Swipe','BankTransfer',"Other"
        ]
        receipt_types = ["FISCAL TAX INVOICE", "DEBIT NOTE", "CREDIT NOTE", "QUOTATION"]

        statsInvoice = []

        # Loop through all receipt types, currencies, and payment methods
        for receipt_type in receipt_types:
            receiptsFull = Receipt.objects.filter(
                date__range=[start, end],
                receipt_type=receipt_type,
                branch=branch
            )

            for currency in currencies:
                for method in payment_methods:
                    receipts = receiptsFull.filter(currency=currency, payment_method=method)
                    if receipts.exists():
                        agg = receipts.aggregate(
                            total_sales=Sum('total'),
                            total_tax=Sum('tax'),
                            total_subtotal=Sum('subtotal'),
                            total_payment=Sum('payment'),
                            total_vat=Sum('Total15VAT'),
                            total_nonvat=Sum('TotalNonVAT'),
                            total_exempt=Sum('TotalExempt'),
                            gross_profit=Sum('profitBT'),
                            net_profit=Sum('profitAT'),
                            avg_invoice=Avg('total'),
                            total_invoices=Count('id'),
                            latest_sale=Max('date'),
                            first_sale=Min('date'),
                        )

                        # Add metadata
                        agg["currency"] = currency
                        agg["method"] = method
                        agg["receipt_type"] = receipt_type

                        # Replace None with 0
                        agg = {k: (v if v is not None else 0) for k, v in agg.items()}

                        statsInvoice.append(agg)

        # Calculate summary by receipt type
        summary_by_type = {}
        for t in receipt_types:
            summary_by_type[t] = sum(x['total_sales'] for x in statsInvoice if x['receipt_type'] == t)

        context = {
            "statsInvoice": statsInvoice,
            "currencies": currencies,
            "payment_methods": payment_methods,
            "differentiator": "Sales",
            "user": "All",
            "start": start,
            "end": end,
            "branch": branch,
            "summary_by_type": summary_by_type
        }

        html = render_to_string("report_template.html", context)
        pdf_path = saveReport(html, f"sales_report_{branch.name}_{start}to{end}")

        if os.path.exists(pdf_path):
            return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')

        return HttpResponse(status=404)
    
    except Exception as e:
        print(str(e))
        return HttpResponse(status=500)
@csrf_exempt
def profit_loss_report(request):
    try:
        branch = Branch.objects.get(id=request.session["branch"])
        data = json.loads(request.body)
        start = datetime.datetime.fromisoformat(data["start"]).date()
        end = datetime.datetime.fromisoformat(data["end"]).date()

        # Transactions in period
        transactions = Transaction.objects.filter(
            date__range=[start, end],
            branch=branch
        )

        # Total sales and tax
        total_sales = transactions.aggregate(total=Sum('total'))['total'] or 0
        total_tax = transactions.aggregate(total=Sum('tax'))['total'] or 0

        # Cost of goods sold (COGS) from stock
        stocks = Stock.objects.filter(branch=branch, created__date__range=[start, end])
        total_cogs = sum([s.buying_price * s.sold for s in stocks])

        # Gross Profit
        gross_profit = total_sales - total_cogs

        # Net Profit = Gross Profit - Expenses (if you track)
        # For now, we assume no other expenses
        net_profit = gross_profit

        context = {
            "branch": branch,
            "start": start,
            "end": end,
            "total_sales": total_sales,
            "total_tax": total_tax,
            "total_cogs": total_cogs,
            "gross_profit": gross_profit,
            "net_profit": net_profit,
            "differentiator": "Profit & Loss Report"
        }

        html = render_to_string("profit_loss_template.html", context)
        pdf_path = saveReport(html, f"profit_loss_{branch.name}_{start}to{end}")

        if os.path.exists(pdf_path):
            return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')

        return HttpResponse(status=404)

    except Exception as e:
        print(str(e))
        return HttpResponse(status=500)
@csrf_exempt
def stock_aging_report(request):
    try:
        branch = Branch.objects.get(id=request.session["branch"])
        data = json.loads(request.body)
        today = datetime.date.today()

        # Optional: filter by expiry date range
        start = datetime.datetime.fromisoformat(data.get("start", today.isoformat())).date()
        end = datetime.datetime.fromisoformat(data.get("end", today.isoformat())).date()

        stocks = Stock.objects.filter(branch=branch)

        stock_data = []
        for stock in stocks:
            days_in_stock = (today - stock.created.date()).days if stock.created else 0
            days_to_expiry = (stock.expiry_date - today).days if stock.expiry_date else None
            stock_data.append({
                "product": stock.product.name if hasattr(stock, 'product') else "Unknown",
                "batch_no": stock.batch_no,
                "quantity": stock.quantity,
                "sold": stock.sold,
                "remaining": stock.quantity - stock.sold,
                "buying_price": stock.buying_price,
                "selling_price": stock.selling_price if hasattr(stock, 'selling_price') else 0,
                "supplier": stock.supplier.name if stock.supplier else "Unknown",
                "created": stock.created.date() if stock.created else None,
                "expiry_date": stock.expiry_date,
                "days_in_stock": days_in_stock,
                "days_to_expiry": days_to_expiry
            })

        context = {
            "branch": branch,
            "stock_data": stock_data,
            "differentiator": "Stock Aging Report",
            "today": today,
            "start": start,
            "end": end
        }

        html = render_to_string("stock_aging_template.html", context)
        pdf_path = saveReport(html, f"stock_aging_{branch.name}_{today}")

        if os.path.exists(pdf_path):
            return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')

        return HttpResponse(status=404)

    except Exception as e:
        print(str(e))
        return HttpResponse(status=500)
@csrf_exempt
def sales_trend_report(request):
    try:
        branch = Branch.objects.get(id=request.session["branch"])
        data = json.loads(request.body)
        start = datetime.datetime.fromisoformat(data["start"]).date()
        end = datetime.datetime.fromisoformat(data["end"]).date()
        group_by = data.get("group_by", "day")  # day, week, month

        transactions = Transaction.objects.filter(
            date__range=[start, end],
            branch=branch,
            receipt_type="FISCAL TAX INVOICE"
        )

        trend_data = {}

        for tx in transactions:
            # Parse date string to date object
            tx_date = datetime.datetime.fromisoformat(tx.date).date() if isinstance(tx.date, str) else tx.date

            if group_by == "day":
                key = tx_date
            elif group_by == "week":
                key = f"{tx_date.isocalendar()[0]}-W{tx_date.isocalendar()[1]}"  # Year-WeekNumber
            elif group_by == "month":
                key = f"{tx_date.year}-{tx_date.month}"
            else:
                key = tx_date

            if key not in trend_data:
                trend_data[key] = 0
            trend_data[key] += float(tx.total)

        # Convert to sorted list
        sorted_trend = sorted(trend_data.items())

        context = {
            "branch": branch,
            "start": start,
            "end": end,
            "trend_data": sorted_trend,
            "differentiator": "Sales Trend Report",
            "group_by": group_by
        }

        html = render_to_string("sales_trend_template.html", context)
        pdf_path = saveReport(html, f"sales_trend_{branch.name}_{start}to{end}")

        if os.path.exists(pdf_path):
            return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')

        return HttpResponse(status=404)

    except Exception as e:
        print(str(e))
        return HttpResponse(status=500)
