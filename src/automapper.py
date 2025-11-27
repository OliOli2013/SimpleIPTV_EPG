import os
import re
import xml.etree.cElementTree as ET
import gzip
import json

class AutoMapper:
    def __init__(self, log_callback=None):
        self.bouquets_path = '/etc/enigma2/'
        self.log = log_callback
        
        # Rozszerzona lista śmieci do wycięcia
        self.junk_words = [
            'HD', 'FHD', 'UHD', '4K', '8K', 'SD', 'HEVC', 'H265', 'H264', 'AAC',
            'PL', 'POL', '(PL)', '[PL]', '|PL|', 'PL.', 'PL:', 'PL-',
            'VIP', 'RAW', 'VOD', 'XXX', 'PREMIUM', 'BACKUP', 'UPDATE',
            'SUB', 'DUB', 'LEKTOR', 'NAPISY',
            'TV', 'CHANNEL', 'STREAM', 'LIVE',
            'PPV', 'PPV1', 'PPV2', 'PPV3', 'PPV4', 'PPV5', 'PPV6',
            'OTV', 'INFO', 'NA', 'ZYWO', 'REC', 'TIMESHIFT',
            'MAC', 'PORTAL', 'KANALY', 'KANAŁY', 'DLA', 'DZIECI',
            'LOW', 'HIGH', 'ORIGINAL', 'SEQ', 'H.', 'P.', 'S.'
        ]

    def _simplify_name(self, name):
        try:
            if not name: return ""
            if isinstance(name, bytes): name = name.decode('utf-8', 'ignore')
            
            name = name.upper()
            
            # Zamieniamy + i &
            name = name.replace('+', 'PLUS').replace('&', 'AND')
            
            # Usuwamy cyfry na początku (np. "1. TVP 1" -> "TVP 1")
            name = re.sub(r'^\d+[\.\)\s]+', '', name)
            
            # Usuwamy znaki specjalne
            name = re.sub(r'[#|_.\-\[\]\(\):]', ' ', name)
            
            parts = name.split()
            # Filtrujemy słowa śmieciowe i pojedyncze litery (chyba że to cyfra)
            clean_parts = []
            for word in parts:
                if word not in self.junk_words:
                    # Zachowaj słowa dłuższe niż 1 znak LUB jeśli są cyfrą (np. "1" w TVP 1)
                    if len(word) > 1 or word.isdigit():
                        clean_parts.append(word)
            
            return "".join(clean_parts)
        except:
            return ""

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
                        if line.startswith('#SERVICE 4097:') or line.startswith('#SERVICE 5001:') or line.startswith('#SERVICE 5002:'):
                            parts = line.split(':')
                            potential_name = parts[-1]
                            
                            # Filtrujemy nagłówki list
                            if "###" in potential_name or "---" in potential_name: continue
                            if len(potential_name) < 2: continue
                                
                            ref_clean = line.replace('#SERVICE ', '').strip()
                            services.append({'full_ref': ref_clean, 'name': potential_name})
                        elif line.startswith('#DESCRIPTION'):
                            if services and "###" not in line:
                                services[-1]['name'] = line.replace('#DESCRIPTION', '').strip()
            except: continue
        return services

    def get_xmltv_channels(self, xml_path):
        """Zwraca słownik { 'ZNORMALIZOWANA_NAZWA': 'XML_ID' }."""
        exact_map = {}
        
        if not os.path.exists(xml_path): return {}
        
        opener = gzip.open if xml_path.endswith('.gz') else open
        if self.log: self.log("Indeksowanie XML...")
        
        try:
            with opener(xml_path, 'rb') as f:
                context = ET.iterparse(f, events=("end",))
                for event, elem in context:
                    if elem.tag == 'channel':
                        xml_id = elem.get('id')
                        display_name = ""
                        for child in elem:
                            if child.tag == 'display-name':
                                display_name = child.text
                                break
                        
                        candidates = []
                        if display_name: candidates.append(self._simplify_name(display_name))
                        # Dodajemy też ID jako kandydata (często lepsze niż nazwa)
                        candidates.append(self._simplify_name(xml_id.replace('.pl', '')))
                        
                        for clean_name in candidates:
                            if clean_name and len(clean_name) > 1:
                                exact_map[clean_name] = xml_id
                                
                        elem.clear()
                    elif elem.tag == 'programme':
                        break
        except Exception: pass
            
        return exact_map

    def generate_mapping(self, xml_path):
        e2_services = self.get_enigma_services()
        if self.log: self.log(f"Analiza {len(e2_services)} kanałów z tunera...")
        
        xml_index = self.get_xmltv_channels(xml_path)
        
        # ZMIANA: Słownik przechowuje LISTY, a nie pojedyncze wartości
        # { "TVP1.pl": ["ref1", "ref2", "ref3"] }
        final_mapping = {}
        
        matched_count = 0
        total_refs_count = 0 # Licznik ile w sumie kanałów podpięliśmy

        if self.log: self.log("Grupowanie kanałów (Multi-Match)...")

        processed = 0
        total = len(e2_services)

        for service in e2_services:
            processed += 1
            if self.log and processed % 2000 == 0:
                self.log(f"Przetworzono {processed}/{total}...")

            try:
                iptv_clean = self._simplify_name(service['name'])
                if len(iptv_clean) < 2: continue

                xml_id = None

                # 1. Dokładne trafienie
                if iptv_clean in xml_index:
                    xml_id = xml_index[iptv_clean]
                
                # 2. Zawieranie (jeśli XML jest częścią nazwy IPTV)
                if not xml_id:
                    for xml_name, xid in xml_index.items():
                        # Warunek: xml_name musi być dłuższe niż 2 znaki
                        if len(xml_name) > 2 and xml_name in iptv_clean:
                            xml_id = xid
                            break
                
                # Jeśli znaleziono dopasowanie
                if xml_id:
                    if xml_id not in final_mapping:
                        final_mapping[xml_id] = []
                        matched_count += 1 # To liczy unikalne kanały XML
                    
                    # Dodaj referencję do listy dla tego kanału
                    final_mapping[xml_id].append(service['full_ref'])
                    total_refs_count += 1

            except Exception: continue

        if self.log: self.log(f"Unikalnych EPG: {matched_count}")
        if self.log: self.log(f"Przypisanych kanałów: {total_refs_count}!")
        
        return final_mapping
