"""
URL configuration for fiskIT project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path

from . import (
    other
    ,views
    )

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .viewsets import *
from fiscalization.viewsets import FiscalReceiptViewSet,FiscalCreditViewSet,FiscalDebitViewSet
# Router for ViewSets
router = DefaultRouter()
router.register(r'branches', BranchViewSet)
router.register(r'customers', CustomerViewSet,basename='customers')
router.register(r'suppliers', SupplierViewSet,basename='suppliers')
router.register(r'currencies', CurrencyViewSet,basename='currencies')
router.register(r'stackholders', StackHolderViewSet,basename='stackholders')
router.register(r'companies', CompanyViewSet,basename='companies')
router.register(r'stocks', StockViewSet,basename='stocks')
router.register(r'pricechanges', PriceChangesViewSet,basename='pricechanges')
router.register(r'products', ProductViewSet, basename='products')
router.register(r'specialprices', SpecialPriceSaleViewSet)
router.register(r'banking', BankingDetailsViewSet)
router.register(r'transactions', TransactionViewSet)
router.register(r'stocktransfers', StockTransferViewSet)
router.register(r'receipts', ReceiptViewSet, basename='receipts')
router.register(r'purchases', PurchaseViewSet, basename='purchases')
router.register(r'returns', ReturnViewSet)
router.register(r'quotations', QuotationViewSet,basename="quotations")
router.register(r'transactionstocks', TransactionStockViewSet)
router.register(r'credits', CreditViewSet,basename='credits')
router.register(r'debits', DebitViewSet,basename='debits')
router.register(r'services', ServiceViewSet)
router.register(r'categories', CategoryViewSet)
router.register(r'nonservices', NonServiceViewSet)
router.register(r'packs', PackViewSet,basename="packs")
router.register(r'promotions', PromotionViewSet)
router.register(r'reportentries', ReportEntryViewSet)
router.register(r'ingredients', IngredientViewSet)
router.register(r'recipes', RecipeViewSet,basename="recipes")
router.register(r'fiscalreceipts',FiscalReceiptViewSet,basename="fiscalreceipts")
router.register(r'fiscalcredits',FiscalCreditViewSet,basename="fiscalcredits")
router.register(r'fiscaldebits',FiscalDebitViewSet,basename="fiscaldebits")



other_patterns=[
path('generate_unique_code/', other.generate_unique_code),
path('stock_take/',other.stock_take),
path('send_invoice_email/<int:receipt_id>/',other.send_invoice_email),   
]
sales_patterns=[


path("make_transfer/", views.make_transfer),

]

pos_urlpatterns=other_patterns
pos_urlpatterns+=sales_patterns
pos_urlpatterns+=[path('', include(router.urls))]
