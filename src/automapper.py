import os
import re
import xml.etree.cElementTree as ET
import gzip

class AutoMapper:
    def __init__(self, log_callback=None):
        self.bouquets_path = '/etc/enigma2/'
        self.log = log_callback

        # JESZCZE BARDZIEJ ROZSZERZONA LISTA ŚMIECI
        # (typowe dopiski z IPTV, sat, list m3u)
        self.junk_words = [
            # rozdzielczości / kodeki
            'HD', 'FHD', 'FULLHD', 'UHD', '4K', '8K', 'SD',
            'HEVC', 'H265', 'H264', 'MPEG4', 'MPEG2', 'AAC', 'AC3', 'EAC3',
            # języki / ścieżki audio
            'PL', 'POL', '(PL)', '[PL]', '|PL|', 'PL.', 'PL:', 'PL-',
            'ENG', 'EN', '(EN)', '[EN]', 'DE', 'GER', 'CZ', 'SK', 'RUS', 'RU',
            'MULTI', 'MULTIAUDIO', 'DUAL', 'NAPISY', 'LEKTOR', 'DUB', 'SUB',
            # dodatki marketingowe
            'VIP', 'VVIP', 'RAW', 'VOD', 'SVOD', 'AVOD', 'XXX',
            'PREMIUM', 'EXTRA', 'MEGA', 'SUPER', 'SUPERHD', 'ULTRA',
            'PLUSHD', 'MAX', 'MAXHD', 'MOBILE', 'LIGHT',
            # techniczne / sieciowe / testowe
            'BACKUP', 'UPDATE', 'TEST', 'BETA', 'OLD', 'ARCHIVE', 'DUMP',
            'LOW', 'HIGH', 'ORIGINAL', 'NEW', 'ALT', 'ALT1', 'ALT2',
            # słowa ogólne, które nic nie wnoszą
            'TV', 'TELEWIZJA', 'CHANNEL', 'KANAL', 'KANAŁ', 'STREAM', 'LIVE',
            'HDTV', 'ONLINE', 'IPTV', 'OTT', 'APP', 'PORTAL',
            # polskie dopiski
            'NA', 'ZYW0', 'ZYW0', 'NAZYW0', 'ŻYWO', 'NAŻYWO',
            'INFO', 'KANALY', 'KANAŁY', 'DLA', 'DZIECI',
            # śmieciowe skróty
            'REC', 'PVR', 'TS', 'TSFILE', 'TIMESHIFT',
            # pseudo-kategorie
            'SPORTOWY', 'FILMOWY', 'SERIALE', 'MOVIE',
            # inne dziwadła z list
            'PL1', 'PL2', 'PL3', 'FHD1', 'FHD2', 'FHD3',
            '4KUHD', 'UHD4K', 'HD4K'
        ]

    def _simplify_name(self, name):
        """
        Czyści i normalizuje nazwę kanału tak, żeby dopasować
        nawet przy różnych dopiskach typu HD/FHD/PL/PREMIUM itp.
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

            # Usuwamy numerowanie typu "01. " na początku
            name = re.sub(r'^\d+[\.\)\s-_]+', '', name)

            # Usuwamy nawiasy z „śmieciami” językowymi / technicznymi
            name = re.sub(r'\((PL|EN|ENG|DE|GER|CZ|SK|RU|RUS|HD|FHD|UHD|4K|8K|HEVC|H265|H264|AC3|EAC3|MULTI|DUB|SUB|LEKTOR|NAPISY)[^)]*\)', ' ', name)
            name = re.sub(r'\[(PL|EN|ENG|DE|GER|CZ|SK|RU|RUS|HD|FHD|UHD|4K|8K|HEVC|H265|H264|AC3|EAC3|MULTI|DUB|SUB|LEKTOR|NAPISY)[^\]]*\]', ' ', name)

            # Usuwamy znaki specjalne → spacje
            name = re.sub(r'[\.\,\#\|\_\-\[\]\(\):/\\!]+', ' ', name)

            # Rozbij na słowa
            parts = name.split()
            clean_parts = []

            for word in parts:
                # pojedyncze litery (bez cyfr) odrzucamy
                if len(word) == 1 and not word.isdigit():
                    continue

                upper_word = word.upper()

                # jeżeli słowo to typowy śmieć – wywalamy
                if upper_word in self.junk_words:
                    continue

                # Słowa zawierające HD/4K itp., ale składające się tylko z tych rzeczy
                if any(tag in upper_word for tag in ['HD', 'FHD', 'UHD', '4K', '8K']) \
                   and not re.search(r'\d', upper_word.replace('4K', '').replace('8K', '')):
                    continue

                clean_parts.append(word)

            # Łączymy z powrotem
            return " ".join(clean_parts).strip()
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
                            if line.startswith('#SERVICE 4097:') or line.startswith('#SERVICE 5001:') \
                               or line.startswith('#SERVICE 5002:') or line.startswith('#SERVICE 1:0:'):
                                parts = line.split(':')
                                potential_name = parts[-1]

                                if "###" in potential_name or "---" in potential_name:
                                    continue
                                if len(potential_name) < 2:
                                    continue

                                ref_clean = line.replace('#SERVICE ', '').strip()
                                services.append({'full_ref': ref_clean, 'name': potential_name})

                        elif line.startswith('#DESCRIPTION'):
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

                        for child in elem:
                            if child.tag == 'display-name' and child.text:
                                display_name = child.text
                                break

                        candidates = []
                        if display_name:
                            candidates.append(self._simplify_name(display_name))
                        if xml_id:
                            candidates.append(self._simplify_name(xml_id.replace('.pl', '')))

                        for clean_name in candidates:
                            if clean_name and len(clean_name) > 1:
                                if clean_name not in exact_map:
                                    exact_map[clean_name] = xml_id

                        elem.clear()
                    elif elem.tag == 'programme':
                        break
        except Exception:
            pass

        return exact_map

    def generate_mapping(self, xml_path):
        """
        Główna logika mapowania:
        - pobiera kanały z Enigmy
        - buduje indeks kanałów z XMLTV
        - dopasowuje (dokładne, zawieranie, podobieństwo tokenów)
        - zwraca:
          { 'XML_ID': ['SERVICE_REF1', 'SERVICE_REF2', ...] }
        """
        e2_services = self.get_enigma_services()
        if self.log:
            self.log(f"Analiza {len(e2_services)} kanałów z tunera...")

        xml_index = self.get_xmltv_channels(xml_path)
        xml_tokens = {name: set(name.split()) for name in xml_index.keys()}

        final_mapping = {}
        matched_unique_epg = 0
        total_refs_count = 0
        total = len(e2_services)
        processed = 0

        if self.log:
            self.log("Grupowanie i dopasowanie kanałów (Multi-Match + fuzzy)...")

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

                if iptv_clean in xml_index:
                    best_xml_id = xml_index[iptv_clean]
                    best_score = 1.0
                else:
                    iptv_tokens = set(iptv_clean.split())

                    for xml_name, xml_id in xml_index.items():
                        if len(xml_name) < 2:
                            continue

                        score = 0.0
                        if xml_name in iptv_clean or iptv_clean in xml_name:
                            score = float(min(len(xml_name), len(iptv_clean))) / float(max(len(xml_name), len(iptv_clean)))
                        else:
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
            self.log(f"Łącznie przypisanych kanałów w tunerze: {total_refs_count}!")

        return final_mapping
