# Planowiec 🗓️

Aplikacja webowa do planowania — kalendarz osobisty, znajomi z udostępnianiem
planów oraz grupy z planami wspólnymi. Flask + Flask-SQLAlchemy + PostgreSQL.

## Struktura projektu

```
planowiec/
├── app.py                  # fabryka aplikacji Flask
├── config.py                # konfiguracja (zmienne środowiskowe)
├── requirements.txt
├── models/                  # warstwa modeli (SQLAlchemy)
│   ├── user_model.py
│   ├── friendship_model.py  # Friendship + PlanAccess (dostęp do planu)
│   ├── activity_model.py    # ActivityType + Activity
│   └── group_model.py       # Group + GroupMember
├── services/                 # logika biznesowa
│   ├── auth_service.py
│   ├── friend_service.py
│   ├── activity_service.py
│   └── group_service.py
├── controllers/              # blueprinty Flask (routing)
│   ├── auth_controller.py       # /auth/...
│   ├── dashboard_controller.py  # /dashboard/... (kalendarz + JSON API)
│   ├── friends_controller.py    # /friends/...
│   ├── groups_controller.py     # /groups/...
│   └── profile_controller.py    # /profile/...
├── static/
│   ├── css/app.css
│   └── js/{app.js, calendar.js}
└── templates/
```

## Wymagania

- Python 3.10+
- PostgreSQL (lokalnie zainstalowany i uruchomiony)

## Instalacja krok po kroku

### 1. Baza danych

Utwórz lokalną bazę PostgreSQL:

```bash
sudo -u postgres psql -c "CREATE DATABASE planowiec;"
sudo -u postgres psql -c "CREATE USER planowiec_user WITH PASSWORD 'haslo';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE planowiec TO planowiec_user;"
```

### 2. Środowisko wirtualne i zależności

```bash
cd planowiec
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Zmienne środowiskowe

```bash
cp .env.example .env
```

Uzupełnij `.env` swoimi danymi dostępowymi do Postgresa (`DB_USER`, `DB_PASSWORD`,
`DB_HOST`, `DB_PORT`, `DB_NAME`) albo podaj bezpośrednio `DATABASE_URL`.
Ustaw też losowy `SECRET_KEY`.

### 4. Uruchomienie

```bash
python app.py
```

Przy pierwszym uruchomieniu aplikacja sama utworzy wszystkie tabele
(`db.create_all()`) oraz domyślne typy aktywności (Praca, Nauka, Sport,
Spotkanie, Odpoczynek, Inne).

Aplikacja wystartuje pod adresem: **http://localhost:5000**

## Funkcje

- **Rejestracja / logowanie** (`/auth/register`, `/auth/login`) — hasła hashowane (Werkzeug).
- **Kalendarz na dashboardzie** (`/dashboard/`) — responsywny widok miesięczny,
  dodawanie/edycja/usuwanie aktywności, własne typy aktywności z kolorami,
  filtrowanie po typie.
- **Znajomi** (`/friends/`) — wyszukiwanie po nazwie/e-mailu, wysyłanie i akceptowanie
  zaproszeń, nadawanie/odbieranie dostępu do podglądu własnego planu (tylko odczyt).
- **Grupy** (`/groups/`) — tworzenie grup, unikalny kod dołączania w formacie
  `PLAN-XXXX-XXXX-XXXX`, dołączanie kodem, plan grupowy edytowalny wyłącznie
  przez administratora grupy, widoczny (tylko do odczytu) dla pozostałych członków.
- **Profil** (`/profile/`) — edycja wyświetlanej nazwy, koloru awatara, zmiana hasła.

## Docker (najszybszy sposób na postawienie appki)

[#docker](#docker)

W repo jest gotowy `Dockerfile` + `docker-compose.yml` (appka + PostgreSQL).

```
cp .env.docker.example .env
# uzupełnij SECRET_KEY, DB_PASSWORD itd. w .env
docker compose up -d --build
```

Appka wystartuje pod `http://localhost:5000` (port konfigurowalny przez `APP_PORT` w `.env`).
Tabele w bazie i domyślne typy aktywności tworzą się automatycznie przy starcie
kontenera (jak w wersji bez Dockera).

## Wystawianie przez Tailscale — uwaga na prefiks

[#wystawianie-przez-tailscale](#wystawianie-przez-tailscale)

**Tailscale Serve NIE dodaje prefiksu automatycznie.** Domyślnie appka
zostanie zamontowana pod `/` na Twoim tailnecie:

```
tailscale serve --bg http://127.0.0.1:5000
```

Jeśli pod tym samym hostname (np. `twoj-node.twoj-tailnet.ts.net`) chodzi
już inna appka pod `/`, powyższa komenda ją **nadpisze**. Żeby uniknąć
kolizji, trzeba jawnie ustawić osobny prefiks ścieżki dla tej appki:

```
tailscale serve --bg --set-path /planowiec http://127.0.0.1:5000
```

Wtedy Twoja druga appka może dalej spokojnie stać pod `/`, a Planowiec
będzie dostępny pod `https://twoj-node.twoj-tailnet.ts.net/planowiec`.

**Ważne:** Tailscale Serve z `--set-path` przekazuje do backendu pełną
ścieżkę razem z prefiksem (nie ścina go). Dlatego appka musi wiedzieć,
pod jakim prefiksem stoi — inaczej połamią się linki, statyczne pliki
i wywołania API. Ta appka jest już na to przygotowana: ustaw zmienną
środowiskową `PREFIX` na dokładnie tę samą wartość, co w `--set-path`:

```
# w .env (Docker) albo jako zmienna środowiskowa procesu
PREFIX=/planowiec
```

Appka sama zamontuje się wtedy pod tym prefiksem (`werkzeug.DispatcherMiddleware`
w `app.py`) — wszystkie linki (`url_for`), pliki statyczne i wywołania API
w JS (`static/js/calendar.js`) automatycznie uwzględnią `/planowiec`.
Żądania bez prefiksu dostaną 404, więc appka na pewno nie „ukradnie”
ścieżki `/` innej aplikacji.

Jeśli appka ma stać **jako jedyna appka pod `/`** na danym hostname —
po prostu zostaw `PREFIX` puste i użyj `tailscale serve` bez `--set-path`.

## Uwagi techniczne

- Widoki cudzych planów (znajomego lub grupy, gdy nie jesteś adminem) korzystają
  z tego samego szablonu kalendarza co własny plan — różnica polega wyłącznie na
  ukryciu przycisków edycji (`can_edit=False`) oraz wymuszeniu trybu tylko-do-odczytu
  po stronie API (`controllers/dashboard_controller.py::_resolve_context`).
- Kod dołączania do grupy jest losowany i sprawdzany pod kątem unikalności
  (`services/group_service.py::generate_unique_code`).
