from django.db import models
from main.models import User,Shift
from django.core.exceptions import ValidationError

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
    taxExclusive=models.DecimalField(max_digits=10, decimal_places=5, editable=False, default=0)  # Tax exclusive amount (uneditable)
    hscode = models.CharField(max_length=10, blank=True, null=True)  # Harmonized System Code
    product_code = models.CharField(max_length=20, unique=True,null=True)  # Unique Product Code
    selling_price = models.DecimalField(max_digits=15, decimal_places=5,null=True)  # Selling price
    tax = models.CharField(max_length=10, choices=TAX_CHOICES, default=15)  # Tax (15%, 0%, or Exempt)
    vat = models.DecimalField(max_digits=10, decimal_places=5, editable=False, default=0)  # VAT amount (uneditable)
    is_service=models.BooleanField(default=False)
    price_changes=models.ManyToManyField("PriceChanges",blank=True)
    def productJsonBody(self,no,production):
       if not production:
       
        if self.tax=="Exempt":
           return {"receiptLineNo":f"{no+1}","receiptLineHSCode":self.hscode,"receiptLinePrice":f"{float(self.selling_price)}","taxID":"1","receiptLineType":"Sale","receiptLineQuantity":f"{self.quantity}","taxCode":"A","receiptLineTotal":float(self.product_total),"receiptLineName":self.name}
        else:
           return {"receiptLineNo":f"{no+1}","receiptLineHSCode":self.hscode,"receiptLinePrice":f"{float(self.selling_price)}","taxID":"3" if self.tax=="15" else "2","taxPercent":self.tax ,"receiptLineType":"Sale","receiptLineQuantity":f"{self.quantity}","taxCode":"C" if self.tax=="15" else "B","receiptLineTotal":float(self.product_total),"receiptLineName":self.name}
       else:
         if self.tax=="Exempt":
           return {"receiptLineNo":f"{no+1}","receiptLineHSCode":self.hscode,"receiptLinePrice":f"{float(self.selling_price)}","taxID":"3","receiptLineType":"Sale","receiptLineQuantity":f"{self.quantity}","taxCode":"C","receiptLineTotal":float(self.product_total),"receiptLineName":self.name}
         else:
           return {"receiptLineNo":f"{no+1}","receiptLineHSCode":self.hscode,"receiptLinePrice":f"{float(self.selling_price)}","taxID":"1" if self.tax=="15" else "2","taxPercent":self.tax ,"receiptLineType":"Sale","receiptLineQuantity":f"{self.quantity}","taxCode":"A" if self.tax=="15" else "B","receiptLineTotal":float(self.product_total),"receiptLineName":self.name}
            
    def todict(self):
        return {"id":self.id,"name":self.name,"profitAT":float(self.profitAT),"profitBT":float(self.profitBT),"hs_code":self.hscode,"product_code":self.product_code,"tax":self.tax,"selling_price":float(self.selling_price),"buying_price":float(self.buying_price),"vat":float(self.vat),"taxExclusive":float(self.taxExclusive),"stock":self.stock,}
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
    invoiceNo=models.TextField(null=True)
    date = models.TextField(null=True)  # Automatically set the date
    time=models.TextField(null=True)
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

