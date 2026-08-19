"""
Punkt wejścia dla serwera produkcyjnego (Gunicorn).

Użycie:
    gunicorn -b 0.0.0.0:5000 wsgi:application

Jeśli zmienna środowiskowa PREFIX jest ustawiona (np. PREFIX=/planowiec),
aplikacja zostanie zamontowana pod tym prefiksem (patrz app.create_wsgi_app),
co jest potrzebne np. przy wystawianiu przez `tailscale serve --set-path`.
"""

from app import create_wsgi_app

application = create_wsgi_app()

# Alias, bo część narzędzi (np. `flask run`, niektóre PaaS-y) szuka "app"
app = application
