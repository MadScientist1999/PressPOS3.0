from django.db import models
from fiscalization.models import OpenDay
from pos.models import Currency
from decimal import Decimal
from django.utils import timezone
"""
class CurrencyReport(models.Model):
    currency = models.ForeignKey("Currency", on_delete=models.CASCADE, null=True, blank=True)

    # Financial fields
    net15 = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    net0 = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    netEx = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    totalNet = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    tax = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    gross15 = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    gross0 = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    grossEx = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    grossTotal = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    creditTotal = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    balances = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    # Document counts
    no_of_receipts = models.PositiveIntegerField(default=0)
    no_of_credits = models.PositiveIntegerField(default=0)
    no_of_debits = models.PositiveIntegerField(default=0)
    total_documents = models.PositiveIntegerField(default=0)
    file=models.FileField(upload_to="FILES/reports",null=True)
    # Metadata
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Currency Report"
        verbose_name_plural = "Currency Reports"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.currency} Report ({self.created_at.strftime('%Y-%m-%d')})"

class XReport(models.Model):
    day = models.ForeignKey("OpenDay", on_delete=models.CASCADE, null=True, blank=True)
    currencies = models.ManyToManyField("CurrencyReport", related_name="xreports")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "X Report"
        verbose_name_plural = "X Reports"
        ordering = ['-created_at']

    def __str__(self):
        return f"XReport for {self.day} ({self.created_at.strftime('%Y-%m-%d')})"
"""