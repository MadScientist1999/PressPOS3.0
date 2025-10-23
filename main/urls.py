"""
URL configuration for main project.

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
from . import auth
from django.conf.urls.static import static
from .settings import FILES_ROOT,FILES_URL,STATICFILES_DIRS
from pos.urls import pos_urlpatterns
from fiscalization.urls import fisc_urlpatterns
from reports.urls import reports_urlpatterns
from django.urls import re_path
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .viewsets import *

# Router for ViewSets
router = DefaultRouter()
router.register(r'users', UserViewSet,basename="users")
router.register(r'shifts', ShiftViewSet,basename="shifts")

urlpatterns = [

    path("login/",auth.log_in),
    path("logout/",auth.log_out),
   
    
]+static(FILES_URL, document_root=FILES_ROOT)+static('/static/', document_root=STATICFILES_DIRS)

urlpatterns+=pos_urlpatterns
urlpatterns+=fisc_urlpatterns
urlpatterns+=reports_urlpatterns
urlpatterns+=[path('', include(router.urls))]

