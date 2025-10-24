from threading import Thread
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from fiscalization.models import FiscalReceipt,FiscalCredit,FiscalDebit
from decimal import Decimal
from .utils import get_cache_key
from .models import (
    Currency, Supplier, Service, NonService,
    StackHolder, Customer, Receipt, Quotation,Stock, Purchase, Debit,Credit,ReportEntry,Recipe
)

# --- Receipts ---
@receiver([post_save, post_delete])
def clear_cache(sender, **kwargs):
    value=f"{sender.__name__.lower()}s"
    key=get_cache_key(value)
    cache.delete(key)
   
@receiver(post_save, sender=Receipt)
@receiver(post_save, sender=Credit)
@receiver(post_save, sender=Debit)
@receiver(post_save, sender=Purchase)
def handle_fiscal_receipt_or_credit(sender, instance, created, **kwargs):
   
    if not created:
        # Run stock adjustment in a background thread
        return  # Only act on new unsubmitted instances

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
