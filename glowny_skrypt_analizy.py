import csv
import pandas as pd
from pyais.stream import IterMessages
from collections import Counter

PLIK_WEJSCIOWY = 'AIS.txt'
PLIK_WYNIKOWY_POSTOJE = 'raport_czas_postojow.csv'
PLIK_WYNIKOWY_STATYSTYKI = 'statystyki_podstawowe.csv'
PLIK_WYNIKOWY_STATYSTYKI_ROZSZERZONE = 'statystyki_rozszerzone.csv'
PLIK_PODSUMOWANIE_TEKSTOWE = 'wyniki_analizy.txt'

def tlumacz_typ_statku(kod):
    if not kod: return "Brak danych"
    kod = int(kod)
    if kod == 30: return "Statek rybacki"
    if kod in [31, 32, 52]: return "Holownik"
    if kod == 35: return "Statek wojskowy"
    if kod == 36: return "Żaglowiec"
    if kod == 37: return "Jacht rekreacyjny"
    if 40 <= kod <= 49: return "Szybki statek (HSC)"
    if kod == 50: return "Statek pilotowy"
    if kod == 51: return "Statek ratowniczy (SAR)"
    if kod == 55: return "Statek policyjny / celny"
    if 60 <= kod <= 69: return "Statek pasażerski"
    if 70 <= kod <= 79: return "Statek towarowy (Cargo)"
    if 80 <= kod <= 89: return "Tankowiec"
    return f"Inny (kod {kod})"
def czytaj_i_naprawiaj(sciezka):
    with open(sciezka, 'r', encoding='utf-8') as f:
        for linia in f:
            linia = linia.strip()
            if not linia: continue
            if '*' not in linia and linia.count(',') >= 6:
                linia = linia[:-2] + '*' + linia[-2:]
            yield linia.encode('utf-8')
print("ETAP 1: Skanuję typy statków...")
pamiec_typow = {}
liczba_wszystkich_linii = 0
liczba_zdekodowanych_ok = 0

for stream_msg in IterMessages(czytaj_i_naprawiaj(PLIK_WEJSCIOWY)):
    liczba_wszystkich_linii += 1
    try:
        zdekodowane = stream_msg.decode()
        liczba_zdekodowanych_ok += 1
        if hasattr(zdekodowane, 'ship_type') and zdekodowane.ship_type:
            if int(zdekodowane.ship_type) != 0:
                pamiec_typow[zdekodowane.mmsi] = zdekodowane.ship_type
    except Exception:
        continue
liczba_unikalnych_statkow = len(pamiec_typow)
rozklad_typow = Counter(tlumacz_typ_statku(v) for v in pamiec_typow.values())

print("ETAP 2: Analizuję sesje postojów w portach / na kotwicy...")
aktywne_postoje = {}
historia_postojow = []

for stream_msg in IterMessages(czytaj_i_naprawiaj(PLIK_WEJSCIOWY)):
    try:
        zdekodowane = stream_msg.decode()
        mmsi = zdekodowane.mmsi
        if mmsi not in pamiec_typow:
            continue
        lat = getattr(zdekodowane, 'lat', None)
        lon = getattr(zdekodowane, 'lon', None)
        predkosc = getattr(zdekodowane, 'speed', None)
        if lat is not None and lon is not None and predkosc is not None:
            if float(predkosc) < 0.5:
                if mmsi not in aktywne_postoje:
                    aktywne_postoje[mmsi] = {'licznik': 1, 'lat': lat, 'lon': lon}
                else:
                    aktywne_postoje[mmsi]['licznik'] += 1
            else:
                if mmsi in aktywne_postoje:
                    zliczone_sygnaly = aktywne_postoje[mmsi]['licznik']
                    if zliczone_sygnaly > 5:
                        historia_postojow.append({
                            'mmsi': mmsi,
                            'typ': tlumacz_typ_statku(pamiec_typow[mmsi]),
                            'lat': aktywne_postoje[mmsi]['lat'],
                            'lon': aktywne_postoje[mmsi]['lon'],
                            'zliczone_sygnaly': zliczone_sygnaly
                        })
                    del aktywne_postoje[mmsi]
    except Exception:
        continue
for mmsi, dane_postoju in aktywne_postoje.items():
    if dane_postoju['licznik'] > 5:
        historia_postojow.append({
            'mmsi': mmsi,
            'typ': tlumacz_typ_statku(pamiec_typow[mmsi]),
            'lat': dane_postoju['lat'],
            'lon': dane_postoju['lon'],
            'zliczone_sygnaly': dane_postoju['licznik']
        })
with open(PLIK_WYNIKOWY_POSTOJE, 'w', newline='', encoding='utf-8-sig') as outfile:
    writer = csv.writer(outfile, delimiter=';')
    writer.writerow(['MMSI', 'Rodzaj statku', 'Szerokosc (Lat)', 'Dlugosc (Lon)', 'Zliczone sygnaly AIS', 'Szacowany czas postoju (Godziny)'])
    for p in historia_postojow:
        godziny = p['zliczone_sygnaly'] * (3 / 60)
        godziny_excel = str(round(godziny, 2)).replace('.', ',')
        writer.writerow([p['mmsi'], p['typ'], p['lat'], p['lon'], p['zliczone_sygnaly'], godziny_excel])
print("ETAP 3: Generuję statystyki końcowe...")

if historia_postojow:
    df = pd.DataFrame(historia_postojow)
    df['Czas_w_godzinach'] = df['zliczone_sygnaly'] * (3 / 60)
    liczba_sesji_przed_filtracja = len(df)
    df_przefiltrowane = df[(df['Czas_w_godzinach'] >= 2) & (df['Czas_w_godzinach'] <= 720)]
    liczba_odrzucone_za_krotkie = len(df[df['Czas_w_godzinach'] < 2])
    liczba_odrzucone_za_dlugie = len(df[df['Czas_w_godzinach'] > 720])
    glowne_klasy = ['Statek towarowy (Cargo)', 'Tankowiec', 'Statek pasażerski']
    df_glowne = df_przefiltrowane[df_przefiltrowane['typ'].isin(glowne_klasy)]
    statystyki = df_glowne.groupby('typ')['Czas_w_godzinach'].agg(
        Liczebnosc_proby='count',
        Sredni_czas_godz='mean',
        Odchylenie_standardowe='std',
        Minimum_godz='min',
        Maksimum_godz='max'
    ).round(2)
    statystyki.to_csv(PLIK_WYNIKOWY_STATYSTYKI, sep=';', decimal=',', encoding='utf-8-sig')
    statystyki_rozszerzone = df_glowne.groupby('typ')['Czas_w_godzinach'].agg(
        Liczebnosc_proby='count',
        Sredni_czas_godz='mean',
        Mediana_godz='median',
        Odchylenie_standardowe='std',
        Q1_godz=lambda x: x.quantile(0.25),
        Q3_godz=lambda x: x.quantile(0.75),
        Minimum_godz='min',
        Maksimum_godz='max',
        Skosnosc=lambda x: x.skew(),
        Kurtoza=lambda x: x.kurt()
    ).round(3)
    statystyki_rozszerzone['Liczba_unikalnych_statkow'] = df_glowne.groupby('typ')['mmsi'].nunique()
    statystyki_rozszerzone.to_csv(PLIK_WYNIKOWY_STATYSTYKI_ROZSZERZONE, sep=';', decimal=',', encoding='utf-8-sig')
    with open(PLIK_PODSUMOWANIE_TEKSTOWE, 'w', encoding='utf-8') as f:
        f.write("=== PODSUMOWANIE ANALIZY ===\n\n")
        f.write("SKANOWANIE I DEKODOWANIE:\n")
        f.write("Liczba przetworzonych linii wejsciowych: %d\n" % liczba_wszystkich_linii)
        f.write("Liczba poprawnie zdekodowanych komunikatow: %d\n" % liczba_zdekodowanych_ok)
        f.write("Liczba unikalnych MMSI z rozpoznanym typem: %d\n\n" % liczba_unikalnych_statkow)
        f.write("Rozklad typow wsrod zidentyfikowanych statkow:\n")
        for typ, ile in rozklad_typow.most_common():
            f.write(f"    {typ}: {ile}\n")
        f.write("\nFILTRACJA SESJI POSTOJOWYCH:\n")
        f.write("Liczba sesji postoju (>5 sygnalow) przed filtracja czasowa: %d\n" % liczba_sesji_przed_filtracja)
        f.write("Odrzucone jako zbyt krotkie (<2h): %d\n" % liczba_odrzucone_za_krotkie)
        f.write("Odrzucone jako zbyt dlugie (>720h): %d\n" % liczba_odrzucone_za_dlugie)
        f.write("Finalna liczba sesji w 3 glownych klasach: %d\n\n" % len(df_glowne))
        f.write("STATYSTYKI ROZSZERZONE PER TYP STATKU:\n")
        f.write(statystyki_rozszerzone.to_string())
        f.write("\n")
    print("-" * 50)
    print("ZAKONCZONO!")
    print(f"Podsumowanie zapisano w: {PLIK_PODSUMOWANIE_TEKSTOWE}")
else:
    print("Nie znaleziono zadnych postojow do wygenerowania statystyk.")