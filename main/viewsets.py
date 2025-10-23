from .serializers import *
from .models import *
from rest_framework import viewsets
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator


@method_decorator(cache_page(60), name='list')
class UserViewSet(viewsets.ModelViewSet):
    queryset=User.objects.all()
    serializer_class = UserSerializer
    
@method_decorator(cache_page(60), name='list')
class ShiftViewSet(viewsets.ModelViewSet):

    serializer_class = ShiftSerializer  
    def get_queryset(self):
        # Base queryset
        qs = Shift.objects.all()

        # Example: filter by date range
        user = self.request.query_params.get('user')
        if user:
            qs = qs.filter(user=user)

        # Add more filters as needed
        return qs