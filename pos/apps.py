# fiscalization/apps.py
from django.apps import AppConfig

class POSConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pos"  # must match your app folder name

    def ready(self):
        import pos.signals  # <- must import here
        print("Signals imported!")  # test if ready() is called
