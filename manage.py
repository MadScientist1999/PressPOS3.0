import sys
import os

# Fix stdout/stderr for PyInstaller
if sys.stdout is None:
    sys.stdout = sys.__stdout__ or open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = sys.__stderr__ or open(os.devnull, "w")

# Set Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'main.settings')

if len(sys.argv) > 1:
    # If arguments are provided, pass them to Django management
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
else:
  
    import uvicorn
    uvicorn.run(
        "main.asgi:application",
        host="0.0.0.0",
        port=8000,
        log_config=None
    )
