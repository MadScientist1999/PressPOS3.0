from django.db import models
from matplotlib import lines
from pos.models import Receipt,Branch,Currency,ReportEntry
from main.settings import HTML_ROOT
class FiscalBranch(Branch):
    
    # Core details
    device_id = models.CharField(max_length=100, null=True, blank=True)
    serial = models.CharField(max_length=100, null=True, blank=True)
    production = models.BooleanField(default=False)
    # File storage
    keystore = models.FileField(upload_to="FILES/certificates/", null=True, blank=True)
    password = models.CharField(max_length=255, null=True, blank=True)
    private_key = models.FileField(upload_to="FILES/certificates/", null=True, blank=True)
    public_key = models.FileField(upload_to="FILES/certificates/", null=True, blank=True) 
    certificate = models.FileField(upload_to="FILES/certificates/", null=True, blank=True)
    globalNo = models.IntegerField(default=1)
    # Derived values
    base_url = models.URLField(max_length=255, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Fiscal Branch"
        verbose_name_plural = "Fiscal Branches"

    def __str__(self):
        return self.name

    def update_base_url(self):
        """Set the base URL depending on production flag and device_id"""
        if self.device_id:
            url = "https://fdmsapi.zimra.co.zw" if self.production else "https://fdmsapitest.zimra.co.zw"
            self.base_url = f"{url}/Device/v1/{self.device_id}/"
            self.save()

class ReceiptError(models.Model):
    code = models.CharField(max_length=10, unique=True)
    severity = models.CharField(
        max_length=10,
        choices=[("RED", "Red"), ("YELLOW", "Yellow")]
    )
    blocks_submission = models.BooleanField(default=False)
    message = models.TextField()

    class Meta:
        verbose_name = "Receipt Error"
        verbose_name_plural = "Receipt Errors"

    def __str__(self):
        return f"{self.code} - {self.message[:50]}"
    
class FiscalReceipt(Receipt):
    
    qrurl=models.TextField(null=True)
    receiptJsonbody = models.TextField(null=True)
    receiptHash = models.TextField(null=True)
    signature=models.TextField(null=True)
    submited=models.BooleanField(default=False,null=True)
    serverResponse=models.TextField(null=True)
    md5_hash=models.TextField(null=True)
    receiptGlobalNo = models.IntegerField(default=1,null=True)
    receiptCounter = models.IntegerField(default=1,null=True)
    result_string=models.TextField(default="",null=True)
    fiscal_branch = models.ForeignKey('FiscalBranch', on_delete=models.CASCADE, null=True)
    errors = models.ManyToManyField(ReceiptError, blank=True)
    day = models.ForeignKey('OpenDay', on_delete=models.CASCADE,null=True)
    verified = models.BooleanField(default=False,null=True)
    verified_at = models.DateTimeField(null=True)
    qrcode=models.FileField(null=True,upload_to=f"{HTML_ROOT}")
    
    def __str__(self):
        return f"{self.receipt_type} - Total: ${self.total}"


            
class FiscalCredit(FiscalReceipt):
    fiscal_receipt=models.ForeignKey(FiscalReceipt,on_delete=models.CASCADE,related_name="fiscal_credit")
    reason=models.TextField(null=True)
    def __str__(self):
        return f"{self.receipt_type} - Total: ${self.total}"

class FiscalDebit(FiscalReceipt):
    fiscal_receipt=models.ForeignKey(FiscalReceipt,on_delete=models.CASCADE,related_name="fiscal_debit")
    reason=models.TextField(null=True)
    def __str__(self):
        return f"{self.receipt_type} - Total: ${self.total}"

class OpenDay(models.Model):
    
    FiscalDayNo = models.IntegerField(null=True)
    FiscalDayOpened = models.TextField(null=True)
    FiscalDayClosed = models.TextField(null=True)
    counter=models.IntegerField(default=1)
    open=models.BooleanField(default=1)
    no_of_receipts_usd=models.IntegerField(default=0)
    no_of_credits_zwl=models.IntegerField(default=0)
    no_of_receipts_zwl=models.IntegerField(default=0)
    no_of_credits_usd=models.IntegerField(default=0)
    branch=models.ForeignKey(FiscalBranch,on_delete=models.CASCADE)
    previousReceiptHash=models.TextField(default="")
    
    def todict(self):
        return {"FiscalDayNo":self.FiscalDayNo,"FiscalDayOpened":self.FiscalDayOpened,"FiscalDayClosed":self.FiscalDayClosed}

class FiscalReportEntry(ReportEntry):

    daily_report = models.ForeignKey("DailyReports", related_name="entries", on_delete=models.CASCADE)
    
    def __str__(self):
        return f"{self.daily_report} - {self.report_type} - {self.currency.code}"

    def get_value(self, report_type, currency_code, tax_percent=None, money_type=None):
    
        qs = self.entries.filter(report_type=report_type, currency__code=currency_code)
        if tax_percent is not None:
            qs = qs.filter(tax_percent=tax_percent)
        if money_type is not None:
            qs = qs.filter(money_type=money_type)
        return sum(entry.value for entry in qs)

class ReceiptCounters(models.Model):
    currency=models.ForeignKey(Currency,on_delete=models.CASCADE,null=True)
    value=models.IntegerField(default=1)
    type=models.TextField(default="")
    day=models.ForeignKey("OpenDay",on_delete=models.CASCADE,null=True)    

class DailyReports(models.Model):
    reportDate = models.TextField(default=0)
    reportTime = models.TextField(default=0)
    FiscalDay = models.ForeignKey("OpenDay", on_delete=models.SET_NULL, null=True, blank=True)
    result_string = models.TextField(default="")
    reportHash = models.TextField(default=0)
    reportSignature = models.TextField(default=0)
    reportJsonbody = models.TextField(default=0)
    fiscalDayStatus = models.TextField(default=0)

    def to_dict(self, production=False):
        data = []

        for entry in self.entries.all():
            item = {
                "fiscalCounterType": entry.report_type,
                "fiscalCounterCurrency": entry.currency.symbol,
                "fiscalCounterValue": round(float(entry.value), 2),
            }

            # Handle tax percent as string
            if entry.tax_percent:
                if entry.tax_percent == "0.00":
                    item["fiscalCounterTaxPercent"] = "0.00"
                    item["fiscalCounterTaxID"] = 2
                elif entry.tax_percent == "15.00":
                    item["fiscalCounterTaxPercent"] = "15.00"
                    item["fiscalCounterTaxID"] = 1 if production else 3
                elif entry.tax_percent == "Exempt":
                    # Don't add taxPercent to dictionary
                    item["fiscalCounterTaxID"] = 3 if production else 1

            if entry.money_type:
                item["fiscalCounterMoneyType"] = entry.money_type

            data.append(item)

        # Only return non-zero values
        return [entry for entry in data if entry.get("fiscalCounterValue", 0.0) != 0.0]

   
    def __str__(self, production=False):
        # Define type order and money type order
        lines =[]
        type_order = [

            "SALEBYTAX",
            "SALETAXBYTAX",
            "CREDITNOTEBYTAX",
            "CREDITNOTETAXBYTAX",
            "DEBITNOTEBYTAX",
            "DEBITNOTETAXBYTAX",
            "BALANCEBYMONEYTYPE"
        ]
        payment_order = ["CASH", "CARD", "MOBILEWALLET", "COUPON", "CREDIT", "BANKTRANSFER", "OTHER"]
        # Define tax order based on environment
        if production:

            tax_order = ["15.00", "0.00", ""]  # Exempt = empty string
        else:
            tax_order = ["", "0.00", "15.00"]
        # Build lines
        for entry in self.entries.all():

            if entry.value == 0:
                continue
            
            type_str = entry.report_type.upper()
            currency_str = entry.currency.symbol.upper()
            if entry.tax_percent is not None:
                if str(entry.tax_percent).lower() == "exempt":

                    tax_or_money_str = ""
                else:
                    tax_or_money_str = f"{float(entry.tax_percent):.2f}"
            elif entry.money_type:
                tax_or_money_str = entry.money_type.upper()
            else:
                tax_or_money_str = ""

            key = (type_str, currency_str, tax_or_money_str)
            value_str = str(int(round(entry.value * 100)))
            lines.append((key, type_str + currency_str + tax_or_money_str + value_str))

        # Sorting function
        def sort_key(x):
            type_idx = type_order.index(x[0][0])
            currency = x[0][1]
            if x[0][0] == "BALANCEBYMONEYTYPE":
                try:
                    money_idx = payment_order.index(x[0][2])
                except ValueError:
                    money_idx = len(payment_order)
                return (type_idx, currency, money_idx)
            else:
                # Use tax_order for tax-based types
                try:
                    tax_idx = tax_order.index(x[0][2])
                except ValueError:
                    tax_idx = len(tax_order)
                return (type_idx, currency, tax_idx)

        # Sort lines
        lines.sort(key=sort_key)

        # Concatenate
        concatenated = "".join(line[1] for line in lines)
        return concatenated

