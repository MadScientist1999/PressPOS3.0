# fiscalization/apps.py
from django.apps import AppConfig

class FiscalizationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "fiscalization"  # must match your app folder name

    def ready(self):
        import fiscalization.signals  # <- must import here
        print("Signals imported!")  # test if ready() is called
