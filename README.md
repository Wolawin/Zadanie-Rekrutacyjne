[README.md](https://github.com/user-attachments/files/32338850/README.md)
# Zadanie-Rekrutacyjne-# Fuel Delivery Reconciliation

## Cel rozwiązania

Rozwiązanie automatyzuje codzienne uzgadnianie dostaw paliwa pomiędzy raportem stacyjnym i dokumentami dostaw z SAP.

Proces:
1. wczytuje i profiluje dane,
2. normalizuje formaty,
3. identyfikuje problemy jakości danych,
4. agreguje dostawy,
5. wykonuje uzgodnienie,
6. klasyfikuje wynik,
7. generuje raport Excel.

## Technologia

Rozwiązanie zostało przygotowane w Pythonie z wykorzystaniem bibliotek pandas i openpyxl.

Python został wybrany, ponieważ głównym problemem jest przetwarzanie, normalizacja, agregacja i uzgadnianie danych, a nie automatyzacja interfejsu użytkownika.

RPA mogłoby zostać wykorzystane jako dodatkowa warstwa integracyjna, jeżeli dane trzeba byłoby pobierać np. z SAP GUI bez dostępnego API lub automatycznego eksportu.

## Struktura

- data/ - pliki wejściowe
- src/ - kod rozwiązania
- output/ - raport wynikowy
- tests.py - testy reguł biznesowych
- requirements.txt - zależności
- README.md - dokumentacja

## Uruchomienie

Instalacja zależności:

    py -m pip install -r requirements.txt

Uruchomienie procesu:

    py .\src\main.py

Uruchomienie testów:

    py .\tests.py

## Reguły biznesowe

Klucz uzgodnienia:

    stacja + data + produkt

Do porównania używana jest ilość rzeczywista z SAP, a nie ilość przeliczona do 15°C.

Jeżeli SAP zawiera kilka dokumentów dla tej samej stacji, daty i produktu, dokumenty są agregowane przed porównaniem.

Tolerancja wynosi większą z wartości:

- 50 litrów
- 0,5% dostawy

Księgowanie SAP w dniu następnym jest klasyfikowane jako DATE_SHIFT, a nie MATCH.

Dokument STO nie jest traktowany jako aktywna dostawa.

## Kategorie uzgodnienia

- MATCH - zgodność w ramach tolerancji
- QUANTITY_DIFFERENCE - różnica powyżej tolerancji
- ONLY_STATION - dostawa tylko po stronie stacji
- ONLY_SAP - dostawa tylko po stronie SAP
- DATE_SHIFT - SAP zaksięgował dostawę dzień później
- STATION_WITH_STO - stacja raportuje dostawę, ale dokument SAP ma status STO

## Data Quality

Problemy jakości danych są raportowane oddzielnie od wyjątków biznesowych.

Rozwiązanie wykrywa między innymi:

- duplikaty,
- powtarzające się numery dokumentów SAP,
- nieprawidłowe daty,
- nieprawidłowe ilości,
- nieznane produkty,
- nieznane statusy,
- przypadki, w których problem jakości danych blokuje wiarygodne uzgodnienie.



## Kontrole wyniku

Raport kontrolny zawiera między innymi:

- liczbę rekordów wejściowych,
- liczbę rekordów po walidacji,
- liczbę zagregowanych dostaw,
- liczbę MATCH,
- liczbę wyjątków według kategorii,
- liczbę problemów Data Quality,
- całkowite wolumeny stacji i SAP.

## Wynik dla dostarczonych danych

Proces uzyskał:

- 42 MATCH
- 1 QUANTITY_DIFFERENCE
- 2 ONLY_STATION
- 1 ONLY_SAP
- 1 STATION_WITH_STO
- 0 DATE_SHIFT
- 5 wyjątków biznesowych
- 6 sygnałów Data Quality

Brak DATE_SHIFT w wyniku oznacza, że dostarczony zestaw danych nie zawiera takiego przypadku. Obsługa DATE_SHIFT jest pokryta testem automatycznym.

## Testy

Zaimplementowano testy dla:

- minimalnej tolerancji 50 l,
- tolerancji 0,5%,
- MATCH,
- QUANTITY_DIFFERENCE,
- DATE_SHIFT,
- STO,
- agregacji wielu dokumentów SAP.

Aktualny wynik:

    7/7 tests passed

## Docelowe działanie unattended


Przebieg:

    Scheduler
        |
        v
    Kontrola plików
        |
        v
    Walidacja struktury
        |
        v
    Normalizacja
        |
        v
    Reconciliation
        |
        v
    Kontrole wyniku
        |
        v
    Raport
        |
        v
    Archiwizacja i powiadomienie

Przed uruchomieniem należy sprawdzić obecność obu plików, ich strukturę, wymagane kolumny oraz kompletność danych.

Retry powinien dotyczyć błędów technicznych, np. chwilowego braku dostępu do pliku. Problemy biznesowe i Data Quality nie powinny powodować automatycznego retry.

Każdy run powinien mieć identyfikator, timestamp, status, log oraz zarchiwizowane wejście i wynik. Powinno być możliwe ponowne przetworzenie konkretnej daty bez usuwania wcześniejszego wyniku.


## Dlaczego Python zamiast RPA?

Najtrudniejszym elementem procesu jest transformacja i uzgodnienie danych, a nie obsługa GUI.

Python zapewnia prosty, deterministyczny, testowalny i wersjonowalny rdzeń.

UiPath lub Power Automate Desktop byłyby uzasadnione jako warstwa integracyjna, gdyby pobranie danych wymagało interakcji z aplikacją bez API lub automatycznego eksportu.
