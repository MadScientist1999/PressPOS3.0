from django.apps import AppConfig
from .license_checker import validate_license
import main.settings as settings

class MyAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "main"

    def ready(self):
        # validate license
        is_valid, message = validate_license()
        settings.LICENSE_VALID = is_valid
        settings.LICENSE_MESSAGE = message
        # import signals so they get registered
        import main.signals

        if not is_valid:
            import sys
            print(message)
            # sys.exit(1)  # uncomment to stop server on invalid license
        else:
            print(message)

      