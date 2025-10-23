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
from . import lists
from . import views

reports_urlpatterns = [
    path('zreport_list/', lists.zreport_list),
    path('reprint_zreport/<int:id>/', views.z_report),
    path("customer_report/<int:customer_id>/",views.customer_report),
    path("supplier_report/<int:supplier_id>/",views.supplier_report),
    path("branch_report/<int:branch_id>/",views.branch_report),
    
    path("user_report/<int:user_id>/",views.user_report),
    
    #path('product_report/product_report/',views.product_report),
    path('stock_sheet/',views.stock_sheet_report),
    
]