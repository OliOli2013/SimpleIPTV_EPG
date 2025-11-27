import os
import re
import xml.etree.cElementTree as ET
import gzip
import json

class AutoMapper:
    def __init__(self, log_callback=None):
        self.bouquets_path = '/etc/enigma2/'
        self.log = log_callback
        
        # Lista słów do usunięcia (tylko najważniejsze dla szybkości)
        self.junk_words = {
            'HD', 'FHD', 'UHD', '4K', '8K', 'SD', 'HEVC', 'H265', 'PL', 'POL', 
            '(PL)', '[PL]', '|PL|', 'VIP', 'RAW', 'VOD', 'XXX', 'PREMIUM', 
            'BACKUP', 'UPDATE', 'TV', 'CHANNEL', 'STREAM', 'LIVE', 
            'PPV', 'OTV', 'INFO', 'NA', 'ZYWO', 'REC', 'MAC', 'PORTAL'
        }

    def _simplify_name(self, name):
        """Szybkie czyszczenie nazwy."""
        try:
            if not name: return ""
            # Szybka konwersja
            if isinstance(name, bytes): name = name.decode('utf-8', 'ignore')
            
            name = name.upper()
            
            # Jeśli nazwa jest krótka, nie mielimy jej regexami
            if len(name) < 3: return name

            # Proste zamiany znaków są szybsze niż regex
            name = name.replace('+', 'PLUS').replace('&', 'AND')
            name = name.replace('.', ' ').replace('-', ' ').replace('_', ' ')
            name = name.replace('(', '').replace(')', '').replace('[', '').replace(']', '')
            
            parts = name.split()
            clean_parts = []
            
            for word in parts:
                if word not in self.junk_words:
                    clean_parts.append(word)
            
            return "".join(clean_parts)
        except:
            return ""

    def get_enigma_services(self):
        services = []
        try:
            files = [f for f in os.listdir(self.bouquets_path) if f.endswith('.tv') and 'userbouquet' in f]
        except: return []

        for filename in files:
            try:
                path = os.path.join(self.bouquets_path, filename)
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('#SERVICE 4097:') or line.startswith('#SERVICE 5001:') or line.startswith('#SERVICE 5002:'):
                            parts = line.split(':')
                            potential_name = parts[-1]
                            
                            if "###" in potential_name or "---" in potential_name: continue
                            
                            # Pobieramy refa
                            ref_clean = line.replace('#SERVICE ', '').strip()
                            services.append({'full_ref': ref_clean, 'name': potential_name})
                        elif line.startswith('#DESCRIPTION'):
                            if services and "###" not in line:
                                services[-1]['name'] = line.replace('#DESCRIPTION', '').strip()
            except: continue
        return services

    def get_xmltv_map(self, xml_path):
        """Tworzy prostą mapę: {UPROSZCZONA_NAZWA: XML_ID}"""
        xml_map = {}
        
        if not os.path.exists(xml_path): return {}
        
        opener = gzip.open if xml_path.endswith('.gz') else open
        if self.log: self.log("Wczytywanie bazy XML...")
        
        try:
            with opener(xml_path, 'rb') as f:
                context = ET.iterparse(f, events=("end",))
                for event, elem in context:
                    if elem.tag == 'channel':
                        xml_id = elem.get('id')
                        
                        # 1. Dodaj po ID (często ID to np. "TVP1.pl")
                        simple_id = self._simplify_name(xml_id.replace('.pl', ''))
                        if simple_id: xml_map[simple_id] = xml_id
                        
                        # 2. Dodaj po Display Name
                        for child in elem:
                            if child.tag == 'display-name':
                                simple_name = self._simplify_name(child.text)
                                if simple_name: xml_map[simple_name] = xml_id
                                break
                        
                        elem.clear()
                    elif elem.tag == 'programme':
                        # Jak dojdziemy do programu, to koniec listy kanałów - przerywamy dla szybkości
                        break
        except Exception: pass
        
        return xml_map

    def generate_mapping(self, xml_path):
        # 1. Pobierz kanały z tunera
        e2_services = self.get_enigma_services()
        if self.log: self.log(f"Znaleziono {len(e2_services)} kanałów w tunerze.")
        
        # 2. Pobierz mapę XML
        xml_map = self.get_xmltv_map(xml_path)
        if self.log: self.log(f"Załadowano bazę XML ({len(xml_map)} wpisów).")
        
        final_mapping = {}
        matched_count = 0
        processed = 0
        total = len(e2_services)

        if self.log: self.log("Błyskawiczne parowanie...")

        for service in e2_services:
            processed += 1
            if self.log and processed % 2000 == 0:
                self.log(f"Przetworzono {processed}/{total}...")

            try:
                # Czyścimy nazwę kanału IPTV (np. "TVP 1 FHD" -> "TVP1")
                simple_name = self._simplify_name(service['name'])
                
                if not simple_name or len(simple_name) < 2: continue

                # Szybki strzał: Czy "TVP1" jest w bazie XML?
                if simple_name in xml_map:
                    xml_id = xml_map[simple_name]
                    
                    if xml_id not in final_mapping:
                        final_mapping[xml_id] = []
                        matched_count += 1
                    
                    final_mapping[xml_id].append(service['full_ref'])
            
            except: continue # Jakikolwiek błąd na kanale - pomiń go i idź dalej

        if self.log: self.log(f"Dopasowano unikalnych: {matched_count}")
        return final_mapping
