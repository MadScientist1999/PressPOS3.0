from django.db import models
from matplotlib import lines
from pos.models import Receipt,Branch,Currency,ReportEntry
from main.settings import HTML_ROOT
import qrcode
from .encryption import *
from decimal import Decimal
from django.db.models import F
import json
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
    fiscal_day = models.ForeignKey('OpenDay', on_delete=models.CASCADE,null=True)
    verified = models.BooleanField(default=False,null=True)
    verified_at = models.DateTimeField(null=True)
    qrcode=models.FileField(null=True,upload_to=f"{HTML_ROOT}")
    _tax_line_concat=None
    _receipt_lines=None
    _receipt_taxes=None
    _tax_line_concat=None
    # Prepare receipt taxes
    def append_tax(self,taxID, code, percent, amount, sales_with_tax):
        self._receipt_taxes.append({
            "taxID": taxID,
            "taxCode": code,
            "taxPercent": percent,
            "taxAmount": round(float(amount), 2) if percent else "0",
            "SalesAmountwithTax": float(self.Total15VAT)
        })
        
    @property
    def receipt_lines(self):
        if self._receipt_lines is None:
            self._receipt_lines = []  # initialize if empty
        return self._receipt_lines
   
    @receipt_lines.setter
    def receipt_lines(self, value):
        self._receipt_lines = value
    @property    
    def receipt_taxes(self):
        self._receipt_taxes = []
        if not self.fiscal_branch.production:
            if self.TotalExempt>0:
             self.append_tax("1", "A", None, 0, self.TotalExempt) 
            if self.TotalNonVAT>0:
             self.append_tax("2", "B", 0.00, 0, self.TotalNonVAT) 
            if self.Total15VAT>0:
             self.append_tax("3", "C", 15.00, self.tax, self.Total15VAT) 
        else:
            if self.Total15VAT>0:
             self.append_tax("1", "A", 15.00, self.tax, self.Total15VAT) 
            if self.TotalNonVAT>0:
             self.append_tax("2", "B", 0.00, 0, self.TotalNonVAT) 
            if self.TotalExempt>0:
             self.append_tax("3", "C", None, 0, self.TotalExempt) 
        return self._receipt_taxes
    
    @receipt_taxes.setter
    def receipt_taxes(self, value):
        self._receipt_taxes = value
        
          
    def add_receipt_line(self, line):
        if self._receipt_lines is None:
            self._receipt_lines = []
        self._receipt_lines.append(line)
    
          
    def add_tax_line(self, line):
        if self._receipt_taxes is None:
            self._receipt_taxes = []
        self._receipt_taxes.append(line)
    @property
    def tax_line_concat(self):
        self._tax_line_concat=""
        
        for taxline in self.receipt_taxes:
            try:
                taxPercentForConcat = "15.00" if float(taxline.get("taxPercent", 0)) == 15.0 else "0.00"
                self._tax_line_concat += (
                f"{taxline['taxCode']}"
                f"{taxPercentForConcat}"
                f"{round(float(taxline['taxAmount']) * 100)}"
                f"{round(float(taxline['SalesAmountwithTax']) * 100)}"
            )
            except Exception as e:
                self._tax_line_concat += f"{taxline['taxCode']}0{round(float(taxline.get('SalesAmountwithTax', 0)) * 100)}"
                print(str(e))
        return self._tax_line_concat
     
    def make_fiscal_values(self):
        mobile_methods = ["Ecocash", "OneMoney", "InnBucks", "Mukuru", "Telecash"]
        
        if self.receipt_type=="FISCAL TAX INVOICE":
            type = 'FISCALINVOICE'
            multiplier="100"
    
        else:
            if self.receipt_type=="CREDIT NOTE":
                multiplier="-100"
                Receipt.objects.filter(id=self.fiscal_receipt.id).update(
                credited=True
                )
            else:
                multiplier="100"
                Receipt.objects.filter(id=self.fiscal_receipt.id).update(
                debited=True
                )
        # Copy products
            type=self.receipt_type.replace(" ","")
        
        self.receiptGlobalNo = self.fiscal_branch.globalNo
        self.receiptCounter = self.fiscal_day.counter
        self.result_string = f"{self.fiscal_branch.device_id}{type}{self.currency.symbol}{self.receiptGlobalNo}{self.created_at_iso}{int(self.total*Decimal(multiplier))}{self.tax_line_concat}{self.fiscal_day.previousReceiptHash if self.fiscal_day.counter != 1 else ''}"
        self.signature = sign_data(self.fiscal_branch, self.result_string)
        self.receiptHash = hash_data(self.result_string)
        self.md5_hash = get_first16chars_of_signature(self.signature)[:16]
        # JSON body for receipt
        self.receiptJsonbody = {
            "receiptLines": self.receipt_lines,
            "receiptType": type,
            "receiptCurrency": self.currency.symbol,
            "receiptPrintForm": "InvoiceA4" if self.isA4 else "Receipt48",
            "receiptDate": self.created_at_iso,
            "receiptPayments": [{"moneyTypeCode": "MobileWallet" if self.payment_method in mobile_methods else self.payment_method, "paymentAmount": round(float(self.payment*Decimal(multiplier)/Decimal("100")), 2)}],
            "receiptTaxes": self.receipt_taxes,
            "receiptTotal": float(Decimal(self.total)*Decimal(multiplier)/Decimal("100")),
            "receiptLinesTaxInclusive": True,
            "invoiceNo": self.invoiceNo
        }
        if not type=="FISCALINVOICE":
             self.receiptJsonbody["creditDebitNote"]={"receiptGlobalNo":f"{self.fiscal_receipt.receiptGlobalNo}","fiscalDayNo":f"{self.fiscal_receipt.fiscal_day.FiscalDayNo}","receiptID":f"{json.loads(self.fiscal_receipt.serverResponse)['receiptID']}"}
             self.receiptJsonbody["ReceiptNotes"]=self.reason
            
        self.receiptJsonbody["receiptDeviceSignature"] = {"signature": self.signature, "hash": self.receiptHash}
        self.receiptJsonbody["receiptGlobalNo"] = self.receiptGlobalNo
        self.receiptJsonbody["receiptCounter"] = self.receiptCounter
        self.receiptJsonbody["invoiceNo"] = self.invoiceNo
        if self.customer:
            self.receiptJsonbody["buyerData"] = {
                "VATNumber": self.customer.vat_number,
                "buyerTradeName": self.customer.tradename,
                "buyerTIN": self.customer.tin_number,
                "buyerRegisterName": self.customer.name,
                "buyerAddress": {
                    "houseNo": self.customer.address,
                    "province": self.customer.province,
                    "city": self.customer.city,
                    "street": self.customer.street
                },
                "buyerContacts": {
                    "email": self.customer.email,
                    "phoneNo": self.customer.phone_number
                }
            }
        

        self.receiptJsonbody = json.dumps({"receipt": self.receiptJsonbody})
        OpenDay.objects.filter(id=self.fiscal_day.id).update(
            counter=F("counter") + 1,
            previousReceiptHash=self.receiptHash
            )
        FiscalBranch.objects.filter(id=self.fiscal_branch.id).update(
            globalNo=F("globalNo") + 1,
        )
        
        
        
        self.qrurl = f"https://{'fdms' if self.fiscal_branch.production else 'fdmstest'}.zimra.co.zw/{self.fiscal_branch.device_id.zfill(10)}{self.day}{self.month}{self.year}{self.receiptGlobalNo:010}{self.md5_hash}"
        qr = qrcode.QRCode(
          version=1,  # Controls the size (1 = smallest, 40 = largest)
          error_correction=qrcode.constants.ERROR_CORRECT_L,  # Low error correction
          box_size=4,  # Size of each QR box
          border=1,  # Border thickness
          )
        qr.add_data(self.qrurl)
        qr.make(fit=True)
        img = qr.make_image(fill="black", back_color="white")
        img.save(f"{HTML_ROOT}/{self.invoiceNo}.png")
        self.qrcode=f"{HTML_ROOT}/{self.invoiceNo}.png"
        
    
    def __str__(self):
        return f"{self.receipt_type} - Total: ${self.total}"


            
class FiscalCredit(FiscalReceipt):
    fiscal_receipt=models.ForeignKey(FiscalReceipt,on_delete=models.CASCADE,related_name="fiscal_credit")
    reason=models.TextField(null=True)
    
    @property
    def receipt_taxes(self):
        return self._receipt_taxes
    @receipt_taxes.setter
    def receipt_taxes(self, value):
        self._receipt_taxes = value
        
    def __str__(self):
        return f"{self.receipt_type} - Total: ${self.total}"

class FiscalDebit(FiscalReceipt):
    fiscal_receipt=models.ForeignKey(FiscalReceipt,on_delete=models.CASCADE,related_name="fiscal_debit")
    reason=models.TextField(null=True)
    @property
    def receipt_taxes(self):
        return self._receipt_taxes
    @receipt_taxes.setter
    def receipt_taxes(self, value):
        self._receipt_taxes = value
    def __str__(self):
        return f"{self.receipt_type} - Total: ${self.total}"


class OpenDay(models.Model):
    
    FiscalDayNo = models.IntegerField(null=True)
    FiscalDayOpened = models.TextField(null=True)
    FiscalDayClosed = models.TextField(null=True)
    counter=models.IntegerField(default=1)
    open=models.BooleanField(default=1)
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

