import os
import re
import xml.etree.cElementTree as ET
import gzip
import json

class AutoMapper:
    def __init__(self, log_callback=None):
        self.bouquets_path = '/etc/enigma2/'
        self.log = log_callback
        
        # --- ROZSZERZONA LISTA SŁÓW ŚMIECIOWYCH ---
        # Wszystkie słowa, które należy wyciąć z nazwy kanału przed dopasowaniem
        self.junk_words = [
            # Jakość i kodeki
            'HD', 'FHD', 'UHD', '4K', '8K', 'SD', 'HEVC', 'H265', 'H264', 'H.264', 'H.265', 'AAC', 'AC3', 'DD+',
            'FULL', 'FULLHD', 'ULTRA', 'ULTRAHD', 'HIGH', 'LOW', 'QUALITY', 'BITRATE',
            
            # Język i region
            'PL', 'POL', 'POLISH', '(PL)', '[PL]', '|PL|', 'PL.', 'PL:', 'PL-', '-PL', '_PL',
            'EN', 'ENG', 'DE', 'GER', 'FR', 'UK', 'USA', 'EU',
            
            # Typy i wersje
            'VIP', 'RAW', 'VOD', 'XXX', 'PREMIUM', 'BACKUP', 'UPDATE', 'TEST',
            'SUB', 'DUB', 'LEKTOR', 'NAPISY', 'SUBS', 'MULTI', 'AUDIO',
            
            # Oznaczenia TV
            'TV', 'CHANNEL', 'KANAL', 'KANAŁ', 'STREAM', 'LIVE', 'TELEWIZJA', 'SAT', 'CABLE', 'IPTV',
            
            # Pay-Per-View i sportowe
            'PPV', 'PPV1', 'PPV2', 'PPV3', 'PPV4', 'PPV5', 'PPV6', 'PPV7', 'PPV8', 'PPV9',
            'EVENT', 'KSW', 'UFC', 'FAME', 'MMA', 'BOXING', 'GALA',
            
            # Przesunięcia czasowe i nagrywanie
            'REC', 'TIMESHIFT', 'TS', 'CATCHUP', 'ARCHIVE', 'REPLAY',
            
            # Inne techniczne i śmieci
            'OTV', 'INFO', 'NA', 'ZYWO', 'NAZYWO', 'NA_ZYWO', 'LIVE', 'ON', 'AIR',
            'MAC', 'PORTAL', 'KANALY', 'KANAŁY', 'DLA', 'DZIECI', 'KIDS',
            'ORIGINAL', 'SEQ', 'H.', 'P.', 'S.', 'M3U', 'LIST',
            'SUPER', 'SUPERHD', 'EXTRA', 'MEGA', 'MAX', 'PLUS', '+'
        ]

    def _simplify_name(self, name):
        """
        Czyści i normalizuje nazwę kanału.
        """
        try:
            if not name:
                return ""
            if isinstance(name, bytes):
                name = name.decode('utf-8', 'ignore')

            # Zamiana na wielkie litery dla ujednolicenia
            name = name.upper()

            # Zamiana znaków specjalnych na spacje
            name = name.replace('+', ' PLUS ')
            name = name.replace('&', ' AND ')
            
            # Usuwamy cyfry i kropki na początku (np. "1. TVP" -> "TVP")
            name = re.sub(r'^\d+[\.\)\:\-\s]+', '', name)

            # Usuwamy wszystko w nawiasach kwadratowych i okrągłych, jeśli to typowe śmieci
            # Ale ostrożnie, żeby nie wyciąć np. (Canal+)
            # Tutaj proste podejście: zamieniamy nawiasy na spacje
            name = re.sub(r'[\.\,\#\|\_\-\[\]\(\)\:\/\\\*\!\?]+', ' ', name)

            # Rozbij na słowa
            parts = name.split()

            clean_parts = []
            for word in parts:
                # Sprawdź czy słowo jest na liście śmieci
                if word in self.junk_words:
                    continue

                # Wywal pojedyncze litery (chyba że to cyfra, np. TVP 1)
                if len(word) == 1 and not word.isdigit():
                    continue

                # Agresywne filtrowanie wzorców typu 'FHD', 'HEVC' jeśli są sklejone
                # np. 'TVN_FHD' -> 'TVN' (po wcześniejszym replace _ na spację już mamy 'TVN FHD')
                # Ale sprawdzamy czy fragment słowa zawiera śmieci
                is_trash = False
                for junk in ['FHD', 'UHD', 'HEVC', 'H265', '1080', '720', '4K']:
                    if junk in word and len(word) < len(junk) + 3: # np. FHDPL
                        is_trash = True
                        break
                if is_trash:
                    continue

                clean_parts.append(word)

            # Łączymy z powrotem
            final_name = " ".join(clean_parts).strip()
            return final_name
        except:
            return ""

    def get_enigma_services(self):
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
                            # Obsługa 4097 (IPTV), 5001/5002 (GStreamer/Exteplayer) oraz 1:0 (DVB)
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

    def get_xmltv_channels(self, xml_path):
        exact_map = {}
        if not os.path.exists(xml_path): return {}

        opener = gzip.open if xml_path.endswith('.gz') else open
        if self.log: self.log("Indeksowanie XMLTV...")

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
                        if display_name: candidates.append(self._simplify_name(display_name))
                        if xml_id: candidates.append(self._simplify_name(xml_id.replace('.pl', '')))

                        for clean_name in candidates:
                            if clean_name and len(clean_name) > 1:
                                if clean_name not in exact_map:
                                    exact_map[clean_name] = xml_id
                        elem.clear()
                    elif elem.tag == 'programme': break
        except: pass
        return exact_map

    def generate_mapping(self, xml_path):
        e2_services = self.get_enigma_services()
        xml_index = self.get_xmltv_channels(xml_path)
        xml_tokens = {name: set(name.split()) for name in xml_index.keys()}
        
        final_mapping = {}
        if self.log: self.log(f"Start parowania: {len(e2_services)} kanałów...")

        for service in e2_services:
            iptv_clean = self._simplify_name(service['name'])
            if len(iptv_clean) < 2: continue

            best_xml_id = None
            best_score = 0.0

            if iptv_clean in xml_index:
                best_xml_id = xml_index[iptv_clean]
                best_score = 1.0
            else:
                iptv_tokens = set(iptv_clean.split())
                for xml_name, xml_id in xml_index.items():
                    if len(xml_name) < 2: continue
                    
                    # Fuzzy match logic
                    if xml_name == iptv_clean: 
                        score = 1.0
                    elif xml_name in iptv_clean or iptv_clean in xml_name:
                        score = 0.85
                    else:
                        tokens_xml = xml_tokens.get(xml_name, set())
                        if not tokens_xml: continue
                        inter = len(iptv_tokens & tokens_xml)
                        if inter == 0: continue
                        score = float(inter) / float(max(len(iptv_tokens), len(tokens_xml)))

                    if score > best_score:
                        best_score = score
                        best_xml_id = xml_id

            if best_xml_id and best_score >= 0.65: # Lekko podniesiony próg dla precyzji
                if best_xml_id not in final_mapping: final_mapping[best_xml_id] = []
                final_mapping[best_xml_id].append(service['full_ref'])

        return final_mapping
