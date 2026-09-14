"""
Wspólna pomocnicza funkcja do wyznaczania "teraz" w TEJ SAMEJ konwencji
czasu co Activity.start_time/end_time — czyli naiwny czas ŚCIENNY
(wall clock) w strefie Europe/Warsaw, NIEZALEŻNIE od strefy czasowej
ustawionej na serwerze/w kontenerze.

Bug, który to naprawia
-----------------------
Kontenery Dockera domyślnie mają systemową strefę czasową UTC (Dockerfile
tego projektu jej nie ustawia). Kod przypomnień liczył dotąd "teraz" przez
`datetime.now()`, co w takim kontenerze zwraca czas UTC, a nie czas lokalny
w Polsce — a `start_time` aktywności jest zapisywany jako naiwny czas
LOKALNY, wpisany wprost z formularza (<input type="datetime-local">).

Latem (czas letni, Polska = UTC+2) dawało to przesunięcie o 2 godziny:
przypomnienie "dzień przed, o 9:00" wysyłało się faktycznie o 11:00 czasu
polskiego, bo scheduler czekał, aż `datetime.now()` (czyli w kontenerze:
UTC) osiągnie naiwną wartość "9:00" — a to odpowiada godzinie 11:00 w
Polsce. Zimą (UTC+1) przesunięcie wynosiłoby analogicznie 1 godzinę.

Rozwiązanie: zamiast API zależnego od strefy systemowej, jawnie liczymy
aktualny czas w strefie Europe/Warsaw i zdejmujemy z niego tzinfo — dzięki
temu wynik jest naiwnym "czasem ściennym" w tej samej konwencji co
start_time/end_time, niezależnie od tego, jaką strefę ma ustawiony
system/kontener, i automatycznie uwzględnia zmianę czasu lato/zima.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

WARSAW_TZ = ZoneInfo("Europe/Warsaw")


def local_now() -> datetime:
    """Naiwny 'teraz' w czasie ściennym Europe/Warsaw (bez tzinfo) — do
    porównywania z Activity.start_time/end_time, które są zapisywane w tej
    samej, naiwnej, lokalnej konwencji."""
    return datetime.now(WARSAW_TZ).replace(tzinfo=None)
