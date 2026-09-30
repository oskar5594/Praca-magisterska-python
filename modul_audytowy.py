import csv
from pyais.stream import IterMessages

PLIK_WEJSCIOWY = 'AIS.txt'
PREFIX_WYNIKOWY = 'wszystkie_statki_baza_'
PLIK_ANOMALII = 'raport_anomalie.txt'
LIMIT_WIERSZY_EXCELA = 1000000

LIMIT_ZANIKU_SYGNALU = 50000

def tlumacz_typ_statku(kod):
    if not kod: return "Brak"
    kod = int(kod)
    if kod == 30: return "Statek rybacki"
    if kod in [31, 32, 52]: return "Holownik"
    if kod == 35: return "Statek wojskowy"
    if kod == 36: return "aglowiec"
    if kod == 37: return "Jacht rekreacyjny"
    if 40 <= kod <= 49: return "Szybki statek (HSC)"
    if kod == 50: return "Statek pilotowy"
    if kod == 51: return "Statek ratowniczy (SAR)"
    if kod == 55: return "Statek policyjny / celny"
    if 60 <= kod <= 69: return "Statek pasażerski"
    if 70 <= kod <= 79: return "Statek towarowy (Cargo)"
    if 80 <= kod <= 89: return "Tankowiec"
    return f"Inny (kod {kod})"
def sprawdz_stan_statku(predkosc):
    try:
        wartosc = float(predkosc)
        if wartosc < 0.5: return "W porcie / Na kotwicy"
        return "W drodze"
    except (ValueError, TypeError):
        return "Nieznany"
def czytaj_i_naprawiaj(sciezka):
    with open(sciezka, 'r', encoding='utf-8') as f:
        for linia in f:
            linia = linia.strip()
            if not linia: continue
            if '*' not in linia and linia.count(',') >= 6:
                linia = linia[:-2] + '*' + linia[-2:]
            yield linia.encode('utf-8')
def otworz_nowy_plik(numer):
    nazwa = f"{PREFIX_WYNIKOWY}{numer}.csv"
    plik = open(nazwa, 'w', newline='', encoding='utf-8')
    pisacz = csv.writer(plik, delimiter=';')
    pisacz.writerow(['MMSI', 'Rodzaj statku', 'Stan', 'Szerokosc', 'Dlugosc', 'Predkosc', 'Kurs (stopnie)', 'Czas (sekunda)'])
    return plik, pisacz
print("ETAP 1: Skanowanie danych. Buduję bazę rozpoznanych statków.")
pamiec_typow = {}

for stream_msg in IterMessages(czytaj_i_naprawiaj(PLIK_WEJSCIOWY)):
    try:
        zdekodowane = stream_msg.decode()
        if hasattr(zdekodowane, 'ship_type') and zdekodowane.ship_type:
            if int(zdekodowane.ship_type) != 0:
                pamiec_typow[zdekodowane.mmsi] = zdekodowane.ship_type
    except Exception:
        continue
print("ETAP 2: Analiza ruchu i wykrywanie anomalii...")
ostatnia_pozycja = {}
ostatnia_obecnosc = {}
lista_anomalii = []

numer_pliku = 1
zapisane_wiersze = 0
licznik_petli = 0
obecny_plik, writer = otworz_nowy_plik(numer_pliku)

for stream_msg in IterMessages(czytaj_i_naprawiaj(PLIK_WEJSCIOWY)):
    licznik_petli += 1
    try:
        zdekodowane = stream_msg.decode()
        mmsi = zdekodowane.mmsi
        if mmsi not in pamiec_typow:
            continue
        lat = getattr(zdekodowane, 'lat', None)
        lon = getattr(zdekodowane, 'lon', None)
        predkosc = getattr(zdekodowane, 'speed', '')
        if lat is not None and lon is not None:
            stan_statku = sprawdz_stan_statku(predkosc)
            if mmsi in ostatnia_obecnosc:
                poprzednia_linia, poprzedni_stan = ostatnia_obecnosc[mmsi]
                roznica_linii = licznik_petli - poprzednia_linia
                if roznica_linii > LIMIT_ZANIKU_SYGNALU and poprzedni_stan == "W drodze":
                    typ = tlumacz_typ_statku(pamiec_typow[mmsi])
                    lista_anomalii.append(f"ANOMALIA: {typ} (MMSI: {mmsi}) zniknął na {roznica_linii} linii, po czym nagle się pojawił.")
            ostatnia_obecnosc[mmsi] = (licznik_petli, stan_statku)
            if mmsi in ostatnia_pozycja and ostatnia_pozycja[mmsi] == (lat, lon):
                continue
            ostatnia_pozycja[mmsi] = (lat, lon)
            if zapisane_wiersze >= LIMIT_WIERSZY_EXCELA:
                obecny_plik.close()
                numer_pliku += 1
                obecny_plik, writer = otworz_nowy_plik(numer_pliku)
                zapisane_wiersze = 0
                print(f"... Zapisano pełny plik. Tworzę część nr {numer_pliku}")
            writer.writerow([
                mmsi,
                tlumacz_typ_statku(pamiec_typow[mmsi]),
                stan_statku,
                lat,
                lon,
                predkosc,
                getattr(zdekodowane, 'course', ''),
                getattr(zdekodowane, 'second', 'Brak')
            ])
            zapisane_wiersze += 1
    except Exception:
        continue
obecny_plik.close()

with open(PLIK_ANOMALII, 'w', encoding='utf-8') as f_anom:
    f_anom.write(f"RAPORT Z WYKRYTYCH ANOMALII (Zanik sygnału powyżej {LIMIT_ZANIKU_SYGNALU} linii)\n")
    f_anom.write("="*70 + "\n")
    if not lista_anomalii:
        f_anom.write("Brak anomalii. Ruch przebiegał poprawnie.\n")
    else:
        for a in lista_anomalii:
            f_anom.write(a + "\n")
print("-" * 50)
print("ANALIZA W PEŁNI ZAKOŃCZONA!")
print(f"Wygenerowano plików CSV: {numer_pliku} (wyeliminowano puste wartości 'Rodzaju statku').")
print(f"Znaleziono {len(lista_anomalii)} anomalii utraty sygnału. Zapisano w {PLIK_ANOMALII}.")