from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    role=models.TextField(null=False, default="")
    def __str__(self):
        return self.username
class Shift(models.Model):
    started=models.DateField(null=True)
    ended=models.DateField(null=True)
    user=models.ForeignKey(User,on_delete=models.CASCADE,null=True)
    