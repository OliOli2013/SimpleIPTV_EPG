import os
import re
import xml.etree.cElementTree as ET
import gzip
import json

class AutoMapper:
    def __init__(self, log_callback=None):
        self.bouquets_path = '/etc/enigma2/'
        self.log = log_callback
        
        # Rozszerzona lista słów śmieciowych do wycinania z nazw
        self.junk_words = [
            'HD', 'FHD', 'UHD', '4K', '8K', 'SD', 'HEVC', 'H265', 'H264', 'AAC',
            'PL', 'POL', '(PL)', '[PL]', '|PL|', 'PL.', 'PL:', 'PL-',
            'VIP', 'RAW', 'VOD', 'XXX', 'PREMIUM', 'BACKUP', 'UPDATE',
            'SUB', 'DUB', 'LEKTOR', 'NAPISY',
            'TV', 'CHANNEL', 'KANAL', 'KANAŁ', 'STREAM', 'LIVE',
            'PPV', 'PPV1', 'PPV2', 'PPV3', 'PPV4', 'PPV5', 'PPV6',
            'OTV', 'INFO', 'NA', 'ZYWO', 'NAZYW0', 'REC', 'TIMESHIFT',
            'MAC', 'PORTAL', 'KANALY', 'KANAŁY', 'DLA', 'DZIECI',
            'LOW', 'HIGH', 'ORIGINAL', 'SEQ', 'H.', 'P.', 'S.',
            'SUPER', 'SUPERHD', 'EXTRA', 'MEGA', 'ULTRA'
        ]

    def _simplify_name(self, name):
        """
        Czyści i normalizuje nazwę kanału tak, żeby dało się dopasować
        nawet przy różnych dopiskach typu HD/PL/PREMIUM/SUPER itp.
        """
        try:
            if not name:
                return ""
            if isinstance(name, bytes):
                name = name.decode('utf-8', 'ignore')

            name = name.upper()

            # Zamiana + i & na słowa
            name = name.replace('+', ' PLUS ')
            name = name.replace('&', ' AND ')

            # Usuwamy cyfry na początku (np. '1. TVP 1' -> 'TVP 1')
            name = re.sub(r'^\d+[\.\)\s]+', '', name)

            # Usuwamy znaki specjalne i zamieniamy je na spacje
            name = re.sub(r'[\.\,\#\|\_\-\[\]\(\):/\\]+', ' ', name)

            # Rozbij na słowa
            parts = name.split()

            clean_parts = []
            for word in parts:
                # Odfiltruj słowa śmieciowe
                if word in self.junk_words:
                    continue

                # Wywal pojedyncze litery (poza cyframi)
                if len(word) == 1 and not word.isdigit():
                    continue

                # Wytnij typowe dopiski typu SUPERHD/FULLHD/4KUHD itd.
                upper_word = word.upper()
                noisy_pattern = any(tag in upper_word for tag in ['HD', 'FHD', 'UHD', '4K', '8K'])
                if noisy_pattern and word in ['HD', 'FHD', 'UHD', '4K', '8K']:
                    # Czyste "HD"/"4K" i podobne – wycinamy
                    continue

                clean_parts.append(word)

            # Łączymy z powrotem w normalny ciąg ze spacjami
            return " ".join(clean_parts)
        except:
            return ""

    def get_enigma_services(self):
        """
        Pobiera listę kanałów z bukietów Enigma2:
        - IPTV: 4097, 5001, 5002
        - DVB (S/T/C): 1:0:...
        Zwraca listę słowników { 'full_ref': ref, 'name': nazwa }.
        """
        services = []
        try:
            files = [f for f in os.listdir(self.bouquets_path) if f.endswith('.tv') and 'userbouquet' in f]
        except OSError:
            return []

        for filename in files:
            try:
                path = os.path.join(self.bouquets_path, filename)
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        line = line.strip()

                        if line.startswith('#SERVICE '):
                            # Obsługa IPTV (jak wcześniej)
                            if line.startswith('#SERVICE 4097:') or line.startswith('#SERVICE 5001:') or line.startswith('#SERVICE 5002:') \
                               or line.startswith('#SERVICE 1:0:'):
                                parts = line.split(':')
                                potential_name = parts[-1]

                                # Filtrujemy nagłówki list / pseudo-kanały
                                if "###" in potential_name or "---" in potential_name:
                                    continue
                                if len(potential_name) < 2:
                                    continue

                                ref_clean = line.replace('#SERVICE ', '').strip()
                                services.append({'full_ref': ref_clean, 'name': potential_name})

                        elif line.startswith('#DESCRIPTION'):
                            # Opis nadpisuje nazwę kanału, jeśli istnieje
                            if services and "###" not in line and "---" not in line:
                                services[-1]['name'] = line.replace('#DESCRIPTION', '').strip()
            except:
                continue
        return services

    def get_xmltv_channels(self, xml_path):
        """
        Indeksuje kanały z XMLTV: zwraca słownik:
        { 'ZNORMALIZOWANA_NAZWA': 'XML_ID' }
        """
        exact_map = {}

        if not os.path.exists(xml_path):
            return {}

        opener = gzip.open if xml_path.endswith('.gz') else open
        if self.log:
            self.log("Indeksowanie kanałów z pliku XMLTV...")

        try:
            with opener(xml_path, 'rb') as f:
                context = ET.iterparse(f, events=("end",))
                for event, elem in context:
                    if elem.tag == 'channel':
                        xml_id = elem.get('id')
                        display_name = ""

                        # Weź pierwszy display-name (często jest ich więcej, ale pierwszy to główna nazwa)
                        for child in elem:
                            if child.tag == 'display-name' and child.text:
                                display_name = child.text
                                break

                        candidates = []

                        # Znormalizowana nazwa z display-name
                        if display_name:
                            candidates.append(self._simplify_name(display_name))

                        # Dodajemy też ID jako kandydata (czasem EPG ma lepsze ID niż nazwę)
                        if xml_id:
                            candidates.append(self._simplify_name(xml_id.replace('.pl', '')))

                        for clean_name in candidates:
                            if clean_name and len(clean_name) > 1:
                                # jeżeli istnieje już taki klucz, nie nadpisujemy na siłę,
                                # zostawiamy pierwsze trafienie jako reprezentatywne
                                if clean_name not in exact_map:
                                    exact_map[clean_name] = xml_id

                        elem.clear()
                    elif elem.tag == 'programme':
                        # jak tylko zaczynają się programme, kończymy kanały
                        break
        except Exception:
            pass

        return exact_map

    def generate_mapping(self, xml_path):
        """
        Główna logika mapowania:
        - pobiera kanały z Enigmy
        - buduje indeks kanałów z XMLTV
        - dopasowuje z różnymi strategiami (dokładne, zawieranie, podobieństwo tokenów)
        - zwraca słownik:
          { 'XML_ID': ['SERVICE_REF1', 'SERVICE_REF2', ...] }
        """
        e2_services = self.get_enigma_services()
        if self.log:
            self.log(f"Analiza {len(e2_services)} kanałów z tunera...")

        xml_index = self.get_xmltv_channels(xml_path)

        # przygotuj tokeny dla kanałów XMLTV, żeby przyspieszyć liczenie podobieństwa
        xml_tokens = {name: set(name.split()) for name in xml_index.keys()}

        final_mapping = {}
        matched_unique_epg = 0
        total_refs_count = 0  # ile łącznie kanałów zostało przypisanych

        if self.log:
            self.log("Grupowanie i dopasowanie kanałów (Multi-Match + fuzzy)...")

        total = len(e2_services)
        processed = 0

        for service in e2_services:
            processed += 1
            if self.log and processed % 2000 == 0:
                self.log(f"Przetworzono {processed}/{total} kanałów z listy...")

            try:
                iptv_name_raw = service['name']
                iptv_clean = self._simplify_name(iptv_name_raw)

                if len(iptv_clean) < 2:
                    continue

                best_xml_id = None
                best_score = 0.0

                # 1. Sprawdzenie: czy jest dokładne dopasowanie po kluczu
                if iptv_clean in xml_index:
                    best_xml_id = xml_index[iptv_clean]
                    best_score = 1.0
                else:
                    # Przygotuj tokeny dla kanału IPTV
                    iptv_tokens = set(iptv_clean.split())

                    # 2. Przelatuj po kanałach XML i szukaj najlepszego podobieństwa
                    for xml_name, xml_id in xml_index.items():
                        # Jeżeli nazwy są bardzo krótkie, pomijamy, żeby uniknąć śmieciowych dopasowań
                        if len(xml_name) < 2:
                            continue

                        # Szybki check – jeśli jeden ciąg zawiera drugi, już jest dość dobre
                        if xml_name in iptv_clean or iptv_clean in xml_name:
                            # nadaj wysoki wynik, ale niekoniecznie 1.0
                            score = float(min(len(xml_name), len(iptv_clean))) / float(max(len(xml_name), len(iptv_clean)))
                        else:
                            # liczymy podobieństwo na podstawie wspólnych tokenów
                            tokens_xml = xml_tokens.get(xml_name, set())
                            if not tokens_xml:
                                continue

                            inter = len(iptv_tokens & tokens_xml)
                            if inter == 0:
                                continue

                            score = float(inter) / float(max(len(iptv_tokens), len(tokens_xml)))

                        if score > best_score:
                            best_score = score
                            best_xml_id = xml_id

                # Uznaj dopasowanie tylko jeśli jest sensowne
                # próg można dostroić (0.5 - 0.7), 0.6 jest zwykle rozsądnym kompromisem
                if best_xml_id and best_score >= 0.6:
                    if best_xml_id not in final_mapping:
                        final_mapping[best_xml_id] = []
                        matched_unique_epg += 1

                    final_mapping[best_xml_id].append(service['full_ref'])
                    total_refs_count += 1

            except Exception:
                continue

        if self.log:
            self.log(f"Unikalnych pozycji EPG (kanałów XMLTV): {matched_unique_epg}")
        if self.log:
            self.log(f"Łącznie przypisanych kanałów w tunerze: {total_refs_count}!")

        return final_mapping
