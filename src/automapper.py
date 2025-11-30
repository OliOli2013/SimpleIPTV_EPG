import os
import re
import xml.etree.cElementTree as ET
import gzip
import json
import time

CACHE_FILE = "/tmp/enigma_services.json"
CACHE_MAX_AGE = 60

def _load_services_cached(bouquets_path):
    if os.path.exists(CACHE_FILE): os.remove(CACHE_FILE)
    services = []
    try:
        files = [f for f in os.listdir(bouquets_path) if f.endswith('.tv') and 'userbouquet' in f]
        for filename in files:
            path = os.path.join(bouquets_path, filename)
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if line.startswith('#SERVICE '):
                        ref = line.replace('#SERVICE ', '').strip()
                        parts = line.split(':')
                        name = parts[-1].strip()
                        if '4097:' in ref or '5001:' in ref or 'http' in ref.lower():
                            services.append({'full_ref': ref, 'name': name})
                    elif line.startswith('#DESCRIPTION') and services:
                        desc = line.replace('#DESCRIPTION', '').strip()
                        if "###" not in desc: services[-1]['name'] = desc
    except: pass
    return services

class AutoMapper:
    def __init__(self, log_callback=None):
        self.bouquets_path = '/etc/enigma2/'
        self.log = log_callback

    # Normalizacja identyczna jak w epgcore
    def _simplify_name(self, text):
        if not text: return ""
        text = text.upper()
        replacements = {'+': 'PLUS', '&': 'AND', '24': 'TWENTYFOUR', 'Ł': 'L', 'Ś': 'S', 'Ć': 'C', 'Ż': 'Z', 'Ź': 'Z', 'Ą': 'A', 'Ę': 'E', 'Ó': 'O', 'Ń': 'N'}
        for old, new in replacements.items(): text = text.replace(old, new)
        trash = ['FULLHD', 'FHD', 'UHD', '4K', 'HEVC', 'H265', 'H.265', 'HD', 'SD', 'PL', 'POL', '(PL)', '[PL]', 'VIP', 'RAW', 'VOD', 'XXX', 'PREMIUM', 'BACKUP', 'TEST', 'SUB', 'DUB', 'LEKTOR', 'OTV', 'V2', 'V3', 'ORG', 'PL:', '|PL|', '[STREAM]', '(TV)', '[YT]', '(YT)', 'TV', 'CHANNEL', 'LIVE', 'POLSKA', 'KANAL', 'POLAND', 'INTERNATIONAL', 'EU', 'EUROPE']
        for t in trash: text = text.replace(t, '')
        text = re.sub(r'[^A-Z0-9\s]', '', text) 
        return text.strip()

    def get_xmltv_channels(self, xml_path):
        norm_map = {}
        if not os.path.exists(xml_path): return {}
        opener = gzip.open if xml_path.endswith('.gz') else open
        try:
            with opener(xml_path, 'rb') as f:
                context = ET.iterparse(f, events=("end",))
                for event, elem in context:
                    if elem.tag == 'channel':
                        xml_id = elem.get('id')
                        display = ""
                        for child in elem:
                            if child.tag == 'display-name': display = child.text; break
                        if xml_id: norm_map[self._simplify_name(xml_id).replace(' ', '')] = xml_id
                        if display: norm_map[self._simplify_name(display).replace(' ', '')] = xml_id
                        elem.clear()
                    elif elem.tag == 'programme': break
        except: pass
        return norm_map

    def generate_mapping(self, xml_path, exclude_refs=None, progress_callback=None):
        if exclude_refs is None: exclude_refs = set()
        services = _load_services_cached(self.bouquets_path)
        xml_map = self.get_xmltv_channels(xml_path)
        
        final = {}
        matched = 0
        total = len(services)
        
        for idx, s in enumerate(services):
            if s['full_ref'] in exclude_refs: continue
            
            name = self._simplify_name(s['name']).replace(' ', '')
            if len(name) < 2: continue
            
            xml_id = xml_map.get(name)
            if not xml_id and len(name) > 3:
                for xk, xid in xml_map.items():
                    if (name in xk or xk in name): xml_id = xid; break
            
            if xml_id:
                final.setdefault(xml_id, []).append(s['full_ref'])
                matched += 1
            
            if progress_callback and idx % 200 == 0: progress_callback(idx, total)
            
        return final
