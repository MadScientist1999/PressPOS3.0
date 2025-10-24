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
from django.urls import include, path
from . import views
from . import remake
from . import signals
from . import other


fisc_urlpatterns = [
    
    path('admin/', admin.site.urls),
    path('get_status/', views.get_status_view),
    path('get_config/', views.get_config_view),
    path('close_day/', views.close_day_view),
    path('open_day/',views.open_day_view),
    path('submit_missing',signals.submitAll),
    path('time_to_close/', other.time_to_close),
    
]
