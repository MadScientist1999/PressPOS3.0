from django.db import models
from main.models import User,Shift
from django.core.exceptions import ValidationError
from decimal import Decimal, ROUND_HALF_UP
from decimal import Decimal, InvalidOperation
from django.http import FileResponse, HttpResponse
from .saver import save
import os
from django.template.loader import render_to_string
class Currency(models.Model):
    name=models.TextField(default="hello")
    symbol = models.TextField(null=True)  # Receipt type
    rate = models.IntegerField(null=True)  # Subtotal amount
   
    def __str__(self):
        return f"{self.symbol}"
    def todict(self):
        return {"id":self.id,"name":self.name,"symbol":self.symbol,"rate":self.rate}

class StackHolder(models.Model):
    name = models.CharField(max_length=100,null=True)  # Customer's name
    tradename=models.CharField(max_length=100,null=True)
    address = models.TextField(blank=True, null=True)  # Address
    street= models.TextField(blank=True, null=True)
    city= models.TextField(blank=True, null=True)
    email = models.EmailField(unique=True,null=True)  # Email address
    phone_number = models.CharField(max_length=15, unique=True,null=True)  # Phone number
    tin_number = models.CharField(max_length=10, null=True)  # Ten-digit TIN number
    vat_number = models.CharField(max_length=9, null=True)  # Nine-digit VAT number
    province=models.CharField(max_length=100,null=True)  # Nine-digit VAT number
    type=models.TextField(default="Customer")
    
    def todict(self):
     return {"id":self.id,"tradename":self.tradename,"name":self.name,"address":self.address,"email":self.email,"phone_number":self.phone_number,"tin_number":self.tin_number,"vat_number":self.vat_number,"province":self.province,"street":self.street,"city":self.city}

    def __str__(self):
        return self.name

class Company(StackHolder):                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            
    def todict(self):
     return {"Name":self.name,"Address":self.address,"Email":self.email,"Phone":self.phone_number,"TIN Number":self.tin_number,"VAT Number":self.vat_number,"Bank":self.bank,"Bank Branch":self.bank_branch,"Account Name":self.account_name,"Account Number":self.account_number,"Bank Account":self.bank_account,"SWIFT Code":self.swift_code}

    def __str__(self):
        return self.name

class Branch(models.Model):
    name = models.CharField(max_length=100,default="")  # Customer's name
    address = models.TextField(blank=True, null=True)  # Address
    street= models.TextField(blank=True, null=True)
    city= models.TextField(blank=True, null=True)
    email = models.EmailField(null=True)  # Email address
    app_password = models.CharField(max_length=100, null=True)  # App password for email
    phone_number = models.CharField(null=True)  # Phone number
    company=models.ForeignKey("Company", on_delete=models.CASCADE,null=True)
    logo=models.FileField(upload_to="FILES/logo/",null=True)
 
class Individual(models.Model):
    last_name = models.CharField(max_length=50, blank=True, null=True)
    national_id=models.CharField(max_length=50, blank=True, null=True)
    class Meta:
        abstract = True

class Customer(StackHolder, Individual):
    balance=models.DecimalField(max_digits=10,default=0,decimal_places=5)
    change=models.DecimalField(max_digits=10,default=0,decimal_places=5)
    customer_type = models.CharField(
        max_length=20,
        choices=[('individual', 'Individual'), ('stakeholder', 'Stakeholder')],
        default='individual'
    )

    def clean(self):
        """Ensure only fields relevant to the selected type are filled."""
        if self.customer_type == 'individual' and (self.tradename or self.tin_number or self.vat_number or self.name or self.address or self.city or self.street):
            raise ValidationError("Individual customers cannot have trade or tax information.")
        if self.customer_type == 'stakeholder' and (self.last_name or self.national_id):
            raise ValidationError("Stakeholder customers cannot have personal information fields.")
        super().clean()


    def __str__(self):
        if self.customer_type == 'individual':
            return f"{self.name} {self.last_name}"
        return f"{self.name}"
   

class Supplier(StackHolder, Individual):
    balance=models.DecimalField(max_digits=10,default=0,decimal_places=5)
    supplier_type = models.CharField(
        max_length=20,
        choices=[('individual', 'Individual'), ('stakeholder', 'Stakeholder')],
        default='individual'
    )

    def clean(self):
        """Ensure only fields relevant to the selected type are filled."""
        if self.supplier_type == 'individual' and (self.tradename or self.tin_number or self.vat_number or self.name or self.address or self.city or self.street):
            raise ValidationError("Individual suppliers cannot have trade or tax information.")
        if self.supplier_type == 'stakeholder' and (self.last_name or self.national_id):
            raise ValidationError("Stakeholder suppliers cannot have personal information fields.")
        super().clean()

 

 

class Stock(models.Model):
    supplier = models.ForeignKey(
        'Supplier',  # Reference to the Supplier model
        on_delete=models.SET_NULL,  # Set to NULL if the supplier is deleted
        null=True,
        blank=True,  # Allow the field to be optional
    )
   
    batch_no=models.IntegerField(default=1)
    sold=models.IntegerField(default=0)
    returned=models.IntegerField(default=0)
    lost=models.IntegerField(default=0)
    buying_price = models.DecimalField(max_digits=15, decimal_places=5)  # Buying price
    profitBT=models.DecimalField(max_digits=10, decimal_places=5, editable=False, default=0)
    profitAT=models.DecimalField(max_digits=10, decimal_places=5, editable=False, default=0)
    quantity=models.IntegerField(default=0)
    branch=models.ForeignKey(Branch,on_delete=models.CASCADE)
    created=models.DateTimeField(null=True)
    expired=models.BooleanField(default=False)
    expiry_date=models.DateField(null=True)    
   
class PriceChanges(models.Model):
    old=models.DecimalField(max_digits=12, decimal_places=5) 
    new=models.DecimalField(max_digits=12, decimal_places=5) 
    changed=models.DateTimeField(null=True)
    user=models.ForeignKey(User,null=True,on_delete=models.CASCADE)
    date=models.DateTimeField(null=True)

class Product(models.Model):
    TAX_CHOICES = [
        ("15", '15%'),
        ("0", '0%'),
        ('Exempt', 'Exempt'),
    ]
    name = models.CharField(max_length=200,unique=True,null=True)  # Product name
    hscode = models.CharField(max_length=10, blank=True, null=True)  # Harmonized System Code
    product_code = models.CharField(max_length=20, unique=True,null=True)  # Unique Product Code
    selling_price = models.DecimalField(max_digits=15, decimal_places=5,null=True)  # Selling price
    tax = models.CharField(max_length=10, choices=TAX_CHOICES, default=15)  # Tax (15%, 0%, or Exempt)
    is_service=models.BooleanField(default=False)
    price_changes=models.ManyToManyField("PriceChanges",blank=True)
    _line_number=None
    _production=None
    @property
    def vat(self):
        """
        Calculate VAT amount based on self.tax
        """
        if self.tax.lower() == "exempt" or self.tax == "0":
            return Decimal("0.00000")
        try:
            tax_percent = Decimal(self.tax) / Decimal("100")
            return (self.selling_price * tax_percent / (Decimal("1") + tax_percent)).quantize(Decimal("0.00001"), rounding=ROUND_HALF_UP)
        except:
            return Decimal("0.00000")

    @property
    def taxExclusive(self):
        """
        Calculate tax-exclusive price
        """
        if self.tax.lower() == "exempt" or self.tax == "0":
            return self.selling_price
        try:
            tax_percent = Decimal(self.tax) / Decimal("100")
            return (self.selling_price / (Decimal("1") + tax_percent)).quantize(Decimal("0.00001"), rounding=ROUND_HALF_UP)
        except:
            return self.selling_price

    @property
    def total(self):
        return self.selling_price * self.quantity

    @property
    def subtotal(self):
        return self.taxExclusive * self.quantity
    @property
    def total_vat(self):
        return self.vat* self.quantity
    @property
    def line_number(self):
        return self._line_number

    @line_number.setter
    def line_number(self, value):
        self._line_number = value
    @property
    def production(self):
        return self._production

    @production.setter
    def production(self, value):
        self._production= value
    
    @property
    def json_body(self):
        """
        Returns JSON representation of the product for receipts.
        Dynamically calculates taxID, taxCode, totals, and line number.
        """
        no = self._line_number
        production = self._production
        tax_id = "2"
        tax_percent = "0"
        tax_code = "B"
        # Determine taxID and taxCode
        if isinstance(self.tax, str) and self.tax.lower() == "exempt":
            tax_id = "3" if production else "1"
            tax_code = "C" if production else "A"
            tax_percent = None
        elif str(self.tax) == "15":
            tax_id = "1" if production else "3"
            tax_code = "A" if production else "C"
            tax_percent = self.tax

        return {
            "receiptLineNo": no + 1,
            "receiptLineHSCode": self.hscode,
            "receiptLinePrice": f"{float(self.selling_price)}",
            "taxID": tax_id,
            "taxPercent": tax_percent,
            "receiptLineType": "Sale",
            "receiptLineQuantity": f"{self.quantity}",
            "taxCode": tax_code,
            "receiptLineTotal": float(self.total),
            "receiptLineName": self.name,
        }

class ReceiptItem(models.Model):
    product = models.ForeignKey("Product", on_delete=models.CASCADE)
    quantity = models.IntegerField()
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    vat = models.DecimalField(max_digits=10, decimal_places=2)

class SpecialPriceSale(models.Model):
    product=models.ForeignKey('Product',on_delete=models.DO_NOTHING,null=True)
    receipt=models.ForeignKey('Receipt',on_delete=models.DO_NOTHING,null=True)
    
class BankingDetails(models.Model):
    bank=models.CharField(max_length=100, null=True)  # Bank name
    bank_branch = models.CharField(max_length=100, null=True)
    account_name = models.CharField(max_length=100, null=True)  # Account name
    account_number = models.CharField(max_length=20, null=True)  # Account number
    bank_account = models.CharField(max_length=34, null=True)  # Bank account number
    swift_code = models.CharField(max_length=11, null=True)  # SWIFT code
    stackholder=models.ForeignKey("StackHolder",null=True,on_delete=models.CASCADE)
    currency=models.ForeignKey("Currency",null=True,on_delete=models.CASCADE)

class Transaction(models.Model):
   
    currency=models.ForeignKey("Currency",
        on_delete=models.SET_NULL,  # Set to NULL if the customer is deleted
        null=True,
        blank=True,  # Allow the field to be optional
            )
    created_at = models.DateTimeField(auto_now_add=True)  # set once
    updated_at = models.DateTimeField(auto_now=True)      # updates on every save
    invoiceNo=models.TextField(null=True)
    receipt_type = models.TextField(max_length=10)  # Receipt type
    subtotal = models.DecimalField(max_digits=12, decimal_places=5,default=0)  # Subtotal amount
    tax = models.DecimalField(max_digits=12, decimal_places=5,default=0)  # Tax amount
    total = models.DecimalField(max_digits=12, decimal_places=5,default=0)  # Total amount
    payment = models.DecimalField(null=True,max_digits=12, decimal_places=5)  # Total amount
    isA4= models.BooleanField(default=False)  # Unlimited stock flag
    Total15VAT = models.FloatField(default=0,)
    TotalNonVAT = models.FloatField(default=0)
    TotalExempt = models.FloatField(default=0)
    payment_method=models.TextField(default="Cash")
    branch=models.ForeignKey(Branch,on_delete=models.CASCADE,null=True)
    file=models.FileField(null=True)
    products=models.ManyToManyField(ReceiptItem,blank=True)
    comment=models.TextField(default="")
    shift=models.ForeignKey(Shift,
                            on_delete=models.CASCADE,
                            null=True
                            )
    user = models.ForeignKey(
        User,  # Reference to the User model
        on_delete=models.DO_NOTHING,
        null=True # Set to NULL if the user is deleted
    )
    
    def generate_document_pdf(self):

        try:
        
            context = {
                "transaction": self,  
            }
            html_content = render_to_string("sale_complete.html", context)
            if self.isA4:    
                    footer_html = render_to_string("footerA4.html", {
                        "transaction": self
                    })
                    header_html = render_to_string("headerA4.html", {
                        "transaction": self
                    })
            else:
                footer_html = None
                header_html = None

            # 3️⃣ Generate PDF using save(), passing both HTMLs
            pdf_path = save(html_content=html_content, filename=f"{self.branch.name}_{self.invoiceNo}", footer_html=footer_html,header_html=header_html)

            if os.path.exists(pdf_path):
                self.file=pdf_path
                self.save()
                return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')
        except Exception as e:
              print(str(e))
              return HttpResponse(status=500)

    @property
    def created_at_iso(self):
        if self.created_at:
            return self.created_at.isoformat(timespec='seconds').split("+")[0]
        return None
    @property
    def day(self):
        return self.created_at.day

    @property
    def month(self):
        return self.created_at.month

    @property
    def year(self):
        return self.created_at.year

    @property
    def time(self):
        return self.created_at.time() 
    
class StockTransfer(Transaction):
    destination=models.ForeignKey(Branch,on_delete=models.CASCADE,null=True,related_name="to")    
   

class Receipt(Transaction):
  
    customer = models.ForeignKey(
        'Customer',  # Reference to the Customer model
        on_delete=models.SET_NULL,  # Set to NULL if the customer is deleted
        null=True,
        blank=True,  # Allow the field to be optional
    )
   
    profitBT=models.DecimalField(max_digits=10, decimal_places=5, editable=False, default=0)
    profitAT=models.DecimalField(max_digits=10, decimal_places=5, editable=False, default=0)
    credited=models.BooleanField(default=False)
    debited=models.BooleanField(default=False)
    on_account=models.BooleanField(default=False)
    change_given=models.BooleanField(default=True)

    
    
    def todict(self):
        payment_method=self.payment_method
        mobile_methods=["Ecocash','OneMoney','InnBucks','Mukuru','Telecash"]
    
        if mobile_methods.__contains__(payment_method):
            payment_method="Mobile"
        elif payment_method=="Swipe":
           payment_method="Swipe"
        elif payment_method=="BankTransfer":
           payment_method="Bank"
        try:
         return {"invoiceNo":self.invoiceNo,"customer":self.customer.todict(),"currency":self.currency.symbol,"payment_method":self.payment_method,"total":self.total}
        except:
          return {"invoiceNo":self.invoiceNo,"currency":self.currency.symbol,"payment_method":self.payment_method,"total":self.total}   
    def __str__(self):
        return f"{self.receipt_type} - Total: ${self.total}"
    
class Purchase(Transaction):
    supplier=models.ForeignKey("Supplier",on_delete=models.CASCADE,null=True)
    returned=models.BooleanField(default=False)

class Return(Purchase):
    reason=models.TextField(null=True)
       
class Quotation(Receipt):
    def __str__(self):
        return f"{self.receipt_type} - Total: ${self.total}"

class TransactionStock(models.Model):
    transaction= models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="stocks_used")
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE)
    quantity = models.IntegerField()
    
class Credit(Receipt):
    receiptCredited=models.ForeignKey(Receipt,on_delete=models.CASCADE,related_name="receipt_credited")
    reason=models.TextField(null=True)
    def __str__(self):
        return f"{self.receipt_type} - Total: ${self.total}"
    
class Debit(Receipt):
    receiptDebited=models.ForeignKey(Receipt,on_delete=models.CASCADE,related_name="receipt_debited")
    reason=models.TextField(null=True)
    def __str__(self):
        return f"{self.receipt_type} - Total: ${self.total}"

class Service(Product):
    def __str__(self):
       return self.name


class Category(models.Model):
    name=models.TextField(null=True)
    description=models.TextField(null=True)
    products=models.ManyToManyField("Product",blank=True)
    
class NonService(Product):
    stock = models.ManyToManyField(Stock,blank=True)
    is_unlimited = models.BooleanField(default=False)  # Unlimited stock flag
    wholesale_price=models.DecimalField(max_digits=10, decimal_places=5, editable=False, default=0)
    wholesale_quantity=models.IntegerField(null=True)
    picture=models.ImageField(null=True,upload_to="FILES/products")
    def adjust_stock(self, stock_available_map, stock_by_nonservice_map):
        """
        Deducts product quantity from available stock and updates sold quantities.
        Returns a list of tuples: (stock_instance, quantity_deducted)
        """
        used_stock_entries = []
        qty_left = getattr(self, "quantity", 0)
        
        for stock in stock_by_nonservice_map.get(self.id, []):
            if qty_left <= 0:
                break

            available = stock_available_map.get(stock.id, Decimal(0))
            if available <= 0:
                continue

            deduct = min(qty_left, available)
            stock.quantity -= deduct
            stock.sold += deduct
            stock.save(update_fields=["quantity", "sold"])

            stock_available_map[stock.id] -= deduct
            qty_left -= deduct
            used_stock_entries.append((stock, deduct))

        return used_stock_entries
    def __str__(self):
        return self.name

class Pack(NonService):
    units=models.IntegerField(default=1)
    nonservice_reference=models.ForeignKey(NonService,on_delete=models.CASCADE,null=True,related_name="reference_product")

class Promotion(Product):
    deadline=models.DateField(null=True)
    rate=models.IntegerField(null=True)

class ReportEntry(models.Model):
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT)
    report_type = models.CharField(max_length=50)
    tax_percent = models.CharField(max_length=10, null=True, blank=True)  # "15.00", "0.00", "Exempt"
    money_type = models.CharField(max_length=50, null=True, blank=True)  # Cash, Card, MobileWallet, etc.
    value = models.DecimalField(max_digits=15, decimal_places=5, default=0)
    fiscal=models.BooleanField(default=False)
    
class Ingredient(models.Model):
    unit=models.DecimalField(max_digits=12, decimal_places=5) 
    product=models.ForeignKey("NonService",on_delete=models.CASCADE,null=True)
class Recipe(NonService):
    ingredients=models.ManyToManyField("Ingredient",blank=True)

