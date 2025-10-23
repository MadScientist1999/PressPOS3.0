from threading import Thread
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from fiscalization.models import FiscalReceipt,FiscalCredit,FiscalDebit
from decimal import Decimal
from .models import (
    Currency, Supplier, Service, NonService,
    StackHolder, Customer, Receipt, Quotation,Stock, Purchase, Debit,Credit,ReportEntry,Recipe
)
@receiver([post_save, post_delete], sender=Currency)
def clear_currency_cache(sender, **kwargs):
    cache.delete("currency_list")
# --- Suppliers ---

@receiver([post_save, post_delete], sender=Supplier)
def clear_supplier_cache(sender, **kwargs):
    cache.delete("supplier_list")

# --- Services ---
@receiver([post_save, post_delete], sender=Service)
def clear_service_cache(sender, **kwargs):
    cache.delete(f"service_list")

# --- NonService Products ---
@receiver([post_save, post_delete], sender=NonService)
def clear_nonservice_cache(sender, **kwargs):
    cache.delete(f"product_list")
    cache.delete(f"nonservice_list")

@receiver([post_save, post_delete], sender=Stock)
@receiver([post_save, post_delete], sender=Receipt)
def clear_product_cache_on_stock_change(sender, instance, **kwargs):
    cache_key = f"product_list"
    cache.delete(cache_key)
    cache_key = f"nonservice_list"
    cache.delete(cache_key)

# --- StackHolders ---
@receiver([post_save, post_delete], sender=StackHolder)
def clear_stackholder_cache(sender, **kwargs):
    cache.delete("stackholder_list")

# --- Customers ---
@receiver([post_save, post_delete], sender=Customer)
def clear_customer_cache(sender, **kwargs):
    cache.delete("customer_list")

# --- Receipts ---
@receiver([post_save, post_delete], sender=Receipt)
@receiver([post_save, post_delete], sender=FiscalReceipt)
@receiver([post_save, post_delete], sender=FiscalCredit)
@receiver([post_save, post_delete], sender=FiscalDebit)
@receiver([post_save, post_delete], sender=Debit)
@receiver([post_save, post_delete], sender=Credit)
def clear_receipt_cache(sender, **kwargs):
    cache.delete(f"receipt_list")
    cache.delete(f"credit_list")
    cache.delete(f"debit_list")

@receiver([post_save, post_delete], sender=Purchase)
def clear_purchase_cache(sender, **kwargs):
    cache.delete(f"purchase_list")
    cache.delete(f"return_list")

@receiver([post_save, post_delete], sender=Recipe)
def clear_recipe_cache(sender, **kwargs):
    cache.delete(f"recipe_list")

# --- Quotations ---
@receiver([post_save, post_delete], sender=Quotation)
def clear_quotation_cache(sender, **kwargs):
    branch_id = kwargs.get('instance').branch.id
    cache.delete(f"quotation_list_branch_{branch_id}")
# Global lock to prevent concurrent processing threads
@receiver(post_save, sender=Receipt)
@receiver(post_save, sender=Credit)
@receiver(post_save, sender=Debit)
@receiver(post_save, sender=Purchase)
def handle_fiscal_receipt_or_credit(sender, instance, created, **kwargs):
    
    if not created:
        # Run stock adjustment in a background thread
        return  # Only act on new unsubmitted instances
 
    from django.db.models import F
    from .models import TransactionStock
    from collections import defaultdict
    
    if sender.__name__=="Credit":
        # Aggregate quantity per stock
        stock_increments = defaultdict(int)
        for ts in TransactionStock.objects.filter(transaction=instance.receiptCredited).select_related("stock"):
            stock_increments[ts.stock_id] += ts.quantity

        # Bulk update stocks
        for stock_id, qty in stock_increments.items():
            Stock.objects.filter(id=stock_id).update(quantity=F('quantity') + qty)
            # Get or create currency
    
    currency=instance.currency
    multiplier = -1 if sender.__name__ == "Credit" or sender.__name__ =="Purchase"  else 1
            
    # Add Sale or Credit Note entries
    def add_entry(report_type, tax_percent, value, money_type=None):
        if value < 0.01:
            return
        entry, _ = ReportEntry.objects.get_or_create(
            currency=currency,
            report_type=report_type,
            tax_percent=tax_percent,
            money_type=money_type,
            defaults={"value": 0},
        )
        entry.value += Decimal(value) * multiplier
        entry.save()
    
    if instance.payment_method == "Cash":
        money_type = "Cash"
    elif instance.payment_method == "OneMoney":
        money_type = "OneMoney"
    elif instance.payment_method == "InnBucks":
        money_type = "InnBucks"
    elif instance.payment_method == "Mukuru":
        money_type = "Mukuru"
    elif instance.payment_method == "Telecash":
        money_type = "Teleash"
    elif instance.payment_method == "Cash":
        money_type = "Cash"
    elif instance.payment_method in ["Card", "Swipe"]:
        money_type = "Card"
    elif instance.payment_method == "Coupon":
        money_type = "Coupon"
    elif instance.payment_method in ["Bank", "BankTranfer"]:
        money_type = "BankTransfer"
    else:
        money_type = "Other"
    
    if sender.__name__ == "FiscalCredit":
        # Credit Note amounts
        add_entry("CreditNoteByTax", "0.00", instance.TotalNonVAT)
        add_entry("CreditNoteByTax", "15.00", instance.Total15VAT)
        add_entry("CreditNoteByTax", "Exempt", instance.TotalExempt)  # Exempt has no tax
        add_entry("CreditNoteTaxByTax", "15.00", instance.tax)
        add_entry("BalanceByMoneyType", None, instance.total, money_type)

    elif sender.__name__ == "FiscalReceipt":  # Sale / Credit Note amounts
        add_entry("SaleByTax", "0.00", instance.TotalNonVAT)
        add_entry("SaleByTax", "15.00", instance.Total15VAT)
        add_entry("SaleByTax", "Exempt", instance.TotalExempt)  # Exempt has no tax
        add_entry("SaleTaxByTax", "15.00", instance.tax)
        add_entry("BalanceByMoneyType", None, instance.total, money_type)

    elif sender.__name__ == "FiscalDebit":  # Sale / Credit Note amounts
        add_entry("DebitNoteByTax", "0.00", instance.TotalNonVAT)
        add_entry("DebitNoteByTax", "15.00", instance.Total15VAT)
        add_entry("DebitNoteByTax", "Exempt", instance.TotalExempt)  # Exempt has no tax
        add_entry("DebitNoteTaxByTax", "15.00", instance.tax)
