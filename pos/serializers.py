from rest_framework import serializers
from .models import Recipe, Ingredient, NonService
import json
class IngredientSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField()  # to send the product ID in POST

    class Meta:
        model = Ingredient
        fields = ['product_id', 'unit']

    def create(self, validated_data):
        product = NonService.objects.get(id=validated_data['product_id'])
        return Ingredient.objects.create(
            product=product,
            recipe=self.context['recipe'],  # pass recipe from parent
            unit=validated_data['unit']
        )
class RecipeSerializer(serializers.ModelSerializer):
    ingredients = IngredientSerializer(many=True)

    class Meta:
        model = Recipe
        fields = ['name', 'product_code', 'hscode', 'tax', 'selling_price', 'ingredients']

    def create(self, validated_data):
        ingredients_data = validated_data.pop('ingredients')
        recipe = Recipe.objects.create(**validated_data)

        for ingredient_data in ingredients_data:
            serializer = IngredientSerializer(data=ingredient_data, context={'recipe': recipe})
            serializer.is_valid(raise_exception=True)
            serializer.save()

        return recipe
from rest_framework import serializers
from decimal import Decimal, ROUND_HALF_UP
from .models import Pack, NonService, Category
import datetime

class PackSerializer(serializers.ModelSerializer):
    nonservice_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = Pack
        fields = [
            'id', 'product_code', 'selling_price', 'units', 
             'nonservice_id'
        ]

    def validate(self, attrs):
        # Convert types
        attrs['units'] = int(attrs['units'])
        attrs['selling_price'] = Decimal(attrs['selling_price'])

        # Validate NonService exists
        try:
            attrs['nonservice'] = NonService.objects.get(id=attrs.pop('nonservice_id'))
        except NonService.DoesNotExist:
            
            raise serializers.ValidationError("Base product not found")

        # Validate units
        if attrs['units'] <= 0:
            raise serializers.ValidationError("Units per pack must be > 0")

        return attrs

    def create(self, validated_data):
        nonservice = validated_data.pop('nonservice')

        # Create the pack
        pack = Pack.objects.create(
            nonservice_reference=nonservice,
            **validated_data
        )

        # Assign categories from base product
        base_categories = Category.objects.filter(products=nonservice)
        product = pack.nonservice_reference.product_ptr
        for category in base_categories:
            category.products.add(product)

        # VAT calculation
        if str(pack.tax) == "15":
            pack.vat = (pack.selling_price * Decimal("0.15") / Decimal("1.15")).quantize(
                Decimal("0.00001"), rounding=ROUND_HALF_UP
            )
            pack.taxExclusive = (pack.selling_price / Decimal("1.15")).quantize(
                Decimal("0.00001"), rounding=ROUND_HALF_UP
            )
        else:
            pack.vat = Decimal("0.00000")
            pack.taxExclusive = pack.selling_price
        pack.save()

        return pack
from rest_framework import serializers
from decimal import Decimal, ROUND_HALF_UP
from .models import *
import datetime
from rest_framework import serializers
from .models import NonService, Service
from django.db.models import Sum, Q

class NonServiceSerializer(serializers.ModelSerializer):
    stock = serializers.SerializerMethodField()

    class Meta:
        model = NonService
        fields = [
            'id', 'name', 'taxExclusive', 'hscode', 'product_code',
            'selling_price', 'tax', 'vat', 'is_service', 'is_unlimited',
            'wholesale_price', 'wholesale_quantity', 'picture', 'price_changes',
            'stock'
        ]
    def create(self, validated_data):
        tax = validated_data.get("tax")
        selling_price = Decimal(validated_data.get("selling_price"))

        if tax == "Exempt":
            vat = Decimal("0.00000")
            tax_exclusive = selling_price
        else:
            tax_rate = Decimal(tax)
            vat = (selling_price * tax_rate / (tax_rate + 100)).quantize(
                Decimal("0.00001"), rounding=ROUND_HALF_UP
            )
            tax_exclusive = (selling_price - vat).quantize(
                Decimal("0.00001"), rounding=ROUND_HALF_UP
            )

        validated_data["vat"] = vat
        validated_data["taxExclusive"] = tax_exclusive

        return super().create(validated_data)
    def get_stock(self, obj):
        # Sum all stock quantities for this product
        return obj.stock.aggregate(total=Sum('quantity'))['total'] or 0


class ServiceSerializer(serializers.ModelSerializer):
    stock = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = [
            'id', 'name', 'taxExclusive', 'hscode', 'product_code',
            'selling_price', 'tax', 'vat', 'is_service', 'is_unlimited',
            'wholesale_price', 'wholesale_quantity', 'picture', 'price_changes',
            'stock'
        ]
    def create(self, validated_data):
        tax = validated_data.get("tax")
        selling_price = Decimal(validated_data.get("selling_price"))

        if tax == "Exempt":
            vat = Decimal("0.00000")
            tax_exclusive = selling_price
        else:
            tax_rate = Decimal(tax)
            vat = (selling_price * tax_rate / (tax_rate + 100)).quantize(
                Decimal("0.00001"), rounding=ROUND_HALF_UP
            )
            tax_exclusive = (selling_price - vat).quantize(
                Decimal("0.00001"), rounding=ROUND_HALF_UP
            )

        validated_data["vat"] = vat
        validated_data["taxExclusive"] = tax_exclusive

        return super().create(validated_data)
    def get_stock(self, obj):
        # Services usually have no stock, so return 0
        return 0
# serializers.py
from rest_framework import serializers
from .models import Branch,Customer,Supplier,Product,Receipt,Credit,Debit

class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = '__all__'

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = '__all__'

class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = '__all__'


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = [
            'id', 'name', 'taxExclusive', 'hscode', 'product_code',
            'selling_price', 'tax', 'vat', 'is_service', 
            'price_changes'
        ]
    
    def get_stock(self, obj):
        # Sum all stock quantities for this product
        try:
            return obj.stock.aggregate(total=Sum('quantity'))['total'] or 0
        except:
            return 0
class ItemSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    product_name = serializers.CharField()
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2)
    selling_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    product_total = serializers.DecimalField(max_digits=12, decimal_places=2)

class QuotationSerializer(serializers.ModelSerializer):
    customer = CustomerSerializer(read_only=True)
    items = ItemSerializer(many=True, write_only=True)

    class Meta:
        model = Quotation
        fields = ["id", "customer", "currency", "subtotal", "tax", "total",
            "invoiceNo", "payment_method", "items","isA4","receipt_type"
        ]
class ReceiptSerializer(serializers.ModelSerializer):
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(), required=False, allow_null=True
    )
    items = ItemSerializer(many=True, write_only=True)
    on_account = serializers.BooleanField(required=False, default=False)
    change_given = serializers.BooleanField(required=False, default=False)
    isA4 = serializers.BooleanField(required=False, default=False)
    payment_method = serializers.CharField(required=False, allow_blank=True)
    payment = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    receipt_type = serializers.CharField(required=False, default="FISCAL TAX INVOICE")
    
    class Meta:
        model = Receipt
        fields = [
        "id", "customer", "currency", "subtotal", "tax", "total",
            "invoiceNo", "payment_method", "items", "isA4", "receipt_type",
             "on_account", "change_given", "payment", "comment",
             # new ones ↓
             "branch", "user", "Total15VAT", "TotalNonVAT",
             "TotalExempt", "profitBT", "profitAT"
        ]

        
class PurchaseSerializer(serializers.ModelSerializer):
    supplier = serializers.PrimaryKeyRelatedField(
        queryset=Supplier.objects.all(), required=False, allow_null=True
    )
    items = ItemSerializer(many=True, write_only=True)
    isA4 = serializers.BooleanField(required=False, default=False)
    payment_method = serializers.CharField(required=False, allow_blank=True)
    payment = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    receipt_type = serializers.CharField(required=False, default="STOCK PURCHASE")

    class Meta:
        model = Purchase
        fields = [
            "id", "supplier", "subtotal", "tax", "total",
            "invoiceNo", "payment_method", "items", "isA4", "receipt_type",
            "payment"
        ]    
class CreditSerializer(serializers.ModelSerializer):
    customer = CustomerSerializer(read_only=True)
    
    class Meta:
        model = Receipt
        fields = '__all__'

class DebitSerializer(serializers.ModelSerializer):
    customer = CustomerSerializer(read_only=True)

    class Meta:
        model = Receipt
        fields = '__all__'
        
class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = '__all__'

class StackHolderSerializer(serializers.ModelSerializer):
    class Meta:
        model = StackHolder
        fields = '__all__'

class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = '__all__'

class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = '__all__'

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = '__all__'

class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = '__all__'

class StockSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stock
        fields = '__all__'

class PriceChangesSerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceChanges
        fields = '__all__'

class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = '__all__'

class SpecialPriceSaleSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpecialPriceSale
        fields = '__all__'

class BankingDetailsSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankingDetails
        fields = '__all__'

class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = '__all__'

class StockTransferSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockTransfer
        fields = '__all__'



class ReturnSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = Receipt
        fields = '__all__'



class TransactionStockSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransactionStock
        fields = '__all__'


class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = "__all__"

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'

class PackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pack
        fields = '__all__'
    def create(self, validated_data):
        nonservice_id = validated_data.pop("nonservice_id")
        packs_to_create = validated_data.pop("packs_to_create", 1)
        branch_id = self.context["request"].session.get("branch")
        branch = Branch.objects.get(id=branch_id)
        
        # Get the base NonService product
        nonservice = NonService.objects.get(id=nonservice_id)

        # Deduct stock
        total_nonservice_stock = sum([s.quantity for s in nonservice.stock.all()])
        units_needed = validated_data["units"] * packs_to_create
        if total_nonservice_stock < units_needed:
            raise serializers.ValidationError("Not enough stock to create the packs")

        qty_left = units_needed
        total_buying_price = Decimal(0)
        for stock_entry in nonservice.stock.order_by("id"):
            if qty_left <= 0:
                break
            deduct = min(stock_entry.quantity, qty_left)
            stock_entry.quantity -= deduct
            stock_entry.save()
            total_buying_price += Decimal(deduct) * stock_entry.buying_price
            qty_left -= deduct

        # Calculate VAT / taxExclusive
        tax = nonservice.tax
        selling_price = validated_data["selling_price"]
        if tax == "15":
            vat = (selling_price * Decimal("0.15") / Decimal("1.15")).quantize(Decimal("0.00001"), rounding=ROUND_HALF_UP)
            tax_exclusive = (selling_price / Decimal("1.15")).quantize(Decimal("0.00001"), rounding=ROUND_HALF_UP)
        else:
            vat = Decimal("0.00000")
            tax_exclusive = selling_price

        # Create the Pack
        pack = Pack.objects.create(
            nonservice_reference=nonservice,
            vat=vat,
            taxExclusive=tax_exclusive,
            hscode=nonservice.hscode,
            name=f"{nonservice.name} {validated_data['units']} pack",
            **validated_data
        )

        # Assign categories from base product
        for category in Category.objects.filter(products=nonservice):
            category.products.add(pack.nonservice_reference.product_ptr)

        # Create stock entry for the pack
        stock = Stock.objects.create(
            batch_no=1,
            quantity=packs_to_create,
            buying_price=total_buying_price,
            branch=branch,
            created=datetime.datetime.now(),
            expired=False
        )
        pack.stock.add(stock)

        return pack

class PromotionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Promotion
        fields = '__all__'

class ReportEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportEntry
        fields = '__all__'

class IngredientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ingredient
        fields = '__all__'

class IngredientInputSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    unit = serializers.DecimalField(max_digits=10, decimal_places=2)
    
class RecipeSerializer(serializers.ModelSerializer):
    stock = serializers.SerializerMethodField()
    ingredients = IngredientSerializer(many=True)

    class Meta:
        model = Recipe
        fields = ["id","name","taxExclusive","hscode","product_code",
        "selling_price","tax","vat","is_service",
        "is_unlimited","wholesale_price","wholesale_quantity","picture",
        "price_changes","stock","ingredients"]
    
    def get_stock(self, obj):
        # Sum all stock quantities for this product
        try:
            return obj.stock.aggregate(total=Sum('quantity'))['total'] or 0
        except:
            return 0
  