"""WSGI entry point for production servers (gunicorn, uWSGI, PythonAnywhere).

PythonAnywhere's default WSGI file expects a module-level name `application`,
while gunicorn is usually pointed at `app:app`. Both work:

    gunicorn wsgi:application
    gunicorn app:app
"""

from app import app as application

# Alias so `gunicorn wsgi:app` also works.
app = application
