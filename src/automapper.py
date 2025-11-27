import os
import re
import xml.etree.cElementTree as ET
import gzip
import json

class AutoMapper:
    def __init__(self, log_callback=None):
        self.bouquets_path = '/etc/enigma2/'
        self.log = log_callback
        
        # --- LISTA SŁÓW ŚMIECIOWYCH (JUNK WORDS) ---
        # Te słowa są całkowicie usuwane przed porównaniem nazw
        self.junk_words = [
            # Jakość / Kodeki
            'HD', 'FHD', 'UHD', '4K', '8K', 'SD', 'HEVC', 'H265', 'H264', 'AVC', 'AAC', 'AC3', 'DD+',
            'FULL', 'FULLHD', 'ULTRA', 'ULTRAHD', 'HIGH', 'LOW', 'QUALITY', 'BITRATE', 'HDR', '1080', '720',
            
            # Język / Kraj
            'PL', 'POL', 'POLISH', '(PL)', '[PL]', '|PL|', 'PL.', 'PL:', 'PL-', '-PL', '_PL',
            'EN', 'ENG', 'DE', 'GER', 'FR', 'UK', 'USA', 'EU', 'INT', 'INTERNATIONAL',
            
            # Wersje / Typy
            'VIP', 'RAW', 'VOD', 'XXX', 'PREMIUM', 'BACKUP', 'UPDATE', 'TEST',
            'SUB', 'DUB', 'LEKTOR', 'NAPISY', 'SUBS', 'MULTI', 'AUDIO', 'ORG', 'ORIGINAL',
            
            # TV / Stream
            'TV', 'CHANNEL', 'KANAL', 'KANAŁ', 'STREAM', 'LIVE', 'TELEWIZJA', 'SAT', 'CABLE', 'IPTV',
            'DVB', 'DVB-T', 'DVB-S', 'OTT',
            
            # PPV / Sport
            'PPV', 'PPV1', 'PPV2', 'PPV3', 'PPV4', 'PPV5', 'PPV6', 'PPV7', 'PPV8', 'PPV9',
            'EVENT', 'KSW', 'UFC', 'FAME', 'MMA', 'BOXING', 'GALA', 'FIGHT',
            
            # Timeshift / Nagrywanie
            'REC', 'TIMESHIFT', 'TS', 'CATCHUP', 'ARCHIVE', 'REPLAY', 'OFFLINE',
            
            # Inne
            'OTV', 'INFO', 'NA', 'ZYWO', 'NAZYWO', 'NA_ZYWO', 'LIVE', 'ON', 'AIR',
            'MAC', 'PORTAL', 'KANALY', 'KANAŁY', 'DLA', 'DZIECI', 'KIDS', 'BAJKI',
            'SEQ', 'H.', 'P.', 'S.', 'M3U', 'LIST', 'PLAYLIST',
            'SUPER', 'SUPERHD', 'EXTRA', 'MEGA', 'MAX', 'PLUS', '+',
            'HOME', 'ENTERTAINMENT', 'MOVIES', 'SERIES', 'FILM', 'CINEMA'
        ]

    def _normalize_string(self, text):
        """
        Tworzy 'odcisk' nazwy (fingerprint).
        Usuwa śmieci, zamienia znaki na słowa, usuwa spacje i znaki specjalne.
        Np. "Canal+ Sport 2 HD [PL]" -> "CANALPLUSSPORT2"
        """
        if not text: return ""
        if isinstance(text, bytes): text = text.decode('utf-8', 'ignore')
        
        # 1. Wielkie litery
        text = text.upper()
        
        # 2. Kluczowe zamiany przed usunięciem znaków
        text = text.replace('+', ' PLUS ')
        text = text.replace('&', ' AND ')
        text = text.replace('ł', 'L').replace('Ł', 'L')
        text = text.replace('ś', 'S').replace('Ś', 'S')
        text = text.replace('ć', 'C').replace('Ć', 'C')
        text = text.replace('ż', 'Z').replace('Ż', 'Z')
        text = text.replace('ź', 'Z').replace('Ź', 'Z')
        text = text.replace('ń', 'N').replace('Ń', 'N')
        text = text.replace('ą', 'A').replace('Ą', 'A')
        text = text.replace('ę', 'E').replace('Ę', 'E')
        text = text.replace('ó', 'O').replace('Ó', 'O')

        # 3. Rozbicie na słowa i filtrowanie śmieci
        # Zamieniamy wszystkie dziwne znaki na spacje
        text = re.sub(r'[^A-Z0-9\s]', ' ', text)
        
        words = text.split()
        clean_words = []
        
        for w in words:
            # Jeśli słowo jest na liście śmieci, pomiń
            if w in self.junk_words:
                continue
            
            # Jeśli słowo zawiera w sobie śmieć (np. TVP1HD), spróbujmy to oczyścić
            # To jest ryzykowne, ale zwiększa skuteczność
            is_junk_embedded = False
            for junk in ['HD', 'FHD', 'UHD', 'PL', 'TV']:
                if junk in w and len(w) > len(junk):
                    # Np. w="TVP1HD", junk="HD". 
                    # Sprawdzamy czy to końcówka
                    if w.endswith(junk):
                        w = w[:-len(junk)] # utnij końcówkę
            
            if len(w) > 0:
                clean_words.append(w)

        # 4. Zlepiamy wszystko w jeden ciąg znaków (bez spacji)
        # To jest klucz do skuteczności: "POLSAT PLAY" == "POLSATPLAY"
        fingerprint = "".join(clean_words)
        
        return fingerprint

    def get_enigma_services(self):
        services = []
        try:
            files = [f for f in os.listdir(self.bouquets_path) if f.endswith('.tv') and 'userbouquet' in f]
        except OSError: return []

        for filename in files:
            try:
                path = os.path.join(self.bouquets_path, filename)
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('#SERVICE '):
                            if any(x in line for x in ['4097:', '5001:', '5002:', '1:0:']):
                                parts = line.split(':')
                                potential_name = parts[-1]
                                if "###" in potential_name or "---" in potential_name: continue
                                if len(potential_name) < 2: continue
                                
                                ref_clean = line.replace('#SERVICE ', '').strip()
                                services.append({'full_ref': ref_clean, 'name': potential_name})
                        elif line.startswith('#DESCRIPTION'):
                            if services and "###" not in line and "---" not in line:
                                services[-1]['name'] = line.replace('#DESCRIPTION', '').strip()
            except: continue
        return services

    def get_xmltv_channels_index(self, xml_path):
        """
        Buduje szybki indeks: { 'FINGERPRINT': 'XML_ID' }
        """
        index = {}
        if not os.path.exists(xml_path): return {}

        opener = gzip.open if xml_path.endswith('.gz') else open
        if self.log: self.log("Indeksowanie kanałów XMLTV...")

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
                        
                        # Generujemy odciski dla ID i Nazwy
                        fps = []
                        if display_name: fps.append(self._normalize_string(display_name))
                        if xml_id: fps.append(self._normalize_string(xml_id.replace('.pl', '')))

                        for fp in fps:
                            if fp and len(fp) > 1:
                                # Jeśli kolizja, pierwszeństwo ma ten wcześniej dodany (zazwyczaj główny)
                                if fp not in index:
                                    index[fp] = xml_id
                        
                        elem.clear()
                    elif elem.tag == 'programme': break
        except Exception as e:
            if self.log: self.log(f"Błąd XML: {e}")
        
        return index

    def generate_mapping(self, xml_path):
        """
        SZYBKA METODA: Słownikowa
        O(N) zamiast O(N*M) - bardzo szybka
        """
        # 1. Pobierz kanały z tunera
        e2_services = self.get_enigma_services()
        if self.log: self.log(f"Pobrano {len(e2_services)} kanałów z tunera.")

        # 2. Zbuduj indeks XMLTV (fingerprint -> xml_id)
        xml_index = self.get_xmltv_channels_index(xml_path)
        if self.log: self.log(f"Zaindeksowano {len(xml_index)} nazw z XMLTV.")

        final_mapping = {}
        matched_count = 0

        # 3. Jednokrotne przejście przez listę kanałów tunera
        if self.log: self.log("Parowanie kanałów (Metoda Fingerprint)...")

        for service in e2_services:
            # Tworzymy odcisk nazwy z tunera
            s_name = service['name']
            s_fp = self._normalize_string(s_name)
            
            if len(s_fp) < 2: continue

            # Szybki lookup w słowniku
            found_id = xml_index.get(s_fp)
            
            # Jeśli nie znaleziono, spróbujmy "fuzzy" ratunku dla trudnych przypadków
            # Np. jeśli s_fp to "CANALPLUSSPORT2" a w xml jest "CANALPLUSSPORT" (bez 2) - to NIE pasuje
            # Ale jeśli w xml jest "CANALPLUSSPORT2FHD" (zostało FHD) -> to może pomóc
            if not found_id:
                # Ostateczna deska ratunku: sprawdzamy czy fingerprint zawiera się w kluczach
                # To spowalnia, więc robimy to tylko dla nieznalezionych
                # (Dla 5000 kanałów może chwilę potrwać, ale warto dla EPG)
                pass 
                # W tej wersji dla wydajności pomijamy full scan.
                # Fingerprint logic jest wystarczająco agresywny w _normalize_string.

            if found_id:
                if found_id not in final_mapping:
                    final_mapping[found_id] = []
                    matched_count += 1
                final_mapping[found_id].append(service['full_ref'])

        if self.log: self.log(f"Dopasowano kanałów: {matched_count}")
        return final_mapping
