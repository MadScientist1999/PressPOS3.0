from rest_framework import serializers
from .models import *
from rest_framework import serializers

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model =User
        fields = '__all__'

class ShiftSerializer(serializers.ModelSerializer):
    class Meta:
        model =Shift
        fields = '__all__'

