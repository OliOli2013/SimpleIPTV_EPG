# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function

SOURCE_DEFINITIONS = [
    {"id": "BMX_AUTO", "label_pl": "BouquetMakerXtream - EPG dostawcy (AUTO)", "label_en": "BouquetMakerXtream - provider EPG (AUTO)", "urls": []},
    {
        "id": "AUTO_AIO",
        "label_pl": "AUTO AIO Polska - zgodność z ustawieniami 2.x",
        "label_en": "AUTO AIO Poland - 2.x settings compatibility",
        "urls": [
            "https://epg.ovh/pltv.gz",
            "https://epgshare01.online/epgshare01/epg_ripper_PL1.xml.gz",
            "https://epg.polishteam.one/guide.xml.gz",
            "https://iptv-epg.org/files/epg-pl.xml.gz",
            "https://epg.pw/xmltv/epg_lite.xml.gz",
        ],
    },
    {
        "id": "AUTO_PL",
        "label_pl": "AUTO Polska - EPG.OVH → EPGShare → EPG.PW",
        "label_en": "AUTO Poland - EPG.OVH → EPGShare → EPG.PW",
        "urls": [
            "https://epg.ovh/pltv.gz",
            "https://epgshare01.online/epgshare01/epg_ripper_PL1.xml.gz",
            "https://epg.polishteam.one/guide.xml.gz",
            "https://iptv-epg.org/files/epg-pl.xml.gz",
            "https://epg.pw/xmltv/epg_lite.xml.gz",
        ],
    },
    {
        "id": "AUTO_PL_RICH",
        "label_pl": "AUTO Polska - rozszerzone opisy",
        "label_en": "AUTO Poland - rich descriptions",
        "urls": [
            "https://epg.ovh/pltv.gz",
            "https://epgshare01.online/epgshare01/epg_ripper_PL1.xml.gz",
            "https://epg.polishteam.one/guide.xml.gz",
            "https://iptv-epg.org/files/epg-pl.xml.gz",
            "https://epg.pw/xmltv/epg_lite.xml.gz",
        ],
    },
    {"id": "EPGOVH_STD", "label_pl": "PL - EPG.OVH standard", "label_en": "PL - EPG.OVH standard", "urls": ["https://epg.ovh/pl.gz"]},
    {"id": "EPGOVH_RICH", "label_pl": "PL - EPG.OVH rich", "label_en": "PL - EPG.OVH rich", "urls": ["https://epg.ovh/pltv.gz"]},
    {"id": "EPGOVH_ARCH", "label_pl": "PL - EPG.OVH 10 dni / archiwum", "label_en": "PL - EPG.OVH 10 days / archive", "urls": ["https://epg.ovh/plar.gz"]},
    {"id": "EPGSHARE_PL1", "label_pl": "PL - EPGShare PL1", "label_en": "PL - EPGShare PL1", "urls": ["https://epgshare01.online/epgshare01/epg_ripper_PL1.xml.gz"]},
    {"id": "EPGSHARE_UK1", "label_pl": "UK - EPGShare UK1", "label_en": "UK - EPGShare UK1", "urls": ["https://epgshare01.online/epgshare01/epg_ripper_UK1.xml.gz"]},
    {"id": "EPGSHARE_DE1", "label_pl": "DE - EPGShare DE1", "label_en": "DE - EPGShare DE1", "urls": ["https://epgshare01.online/epgshare01/epg_ripper_DE1.xml.gz"]},
    {"id": "EPGSHARE_FR1", "label_pl": "FR - EPGShare FR1", "label_en": "FR - EPGShare FR1", "urls": ["https://epgshare01.online/epgshare01/epg_ripper_FR1.xml.gz"]},
    {"id": "EPGSHARE_IT1", "label_pl": "IT - EPGShare IT1", "label_en": "IT - EPGShare IT1", "urls": ["https://epgshare01.online/epgshare01/epg_ripper_IT1.xml.gz"]},
    {"id": "EPGSHARE_ES1", "label_pl": "ES - EPGShare ES1", "label_en": "ES - EPGShare ES1", "urls": ["https://epgshare01.online/epgshare01/epg_ripper_ES1.xml.gz"]},
    {"id": "EPGSHARE_CZ1", "label_pl": "CZ - EPGShare CZ1", "label_en": "CZ - EPGShare CZ1", "urls": ["https://epgshare01.online/epgshare01/epg_ripper_CZ1.xml.gz"]},
    {"id": "EPGSHARE_SK1", "label_pl": "SK - EPGShare SK1", "label_en": "SK - EPGShare SK1", "urls": ["https://epgshare01.online/epgshare01/epg_ripper_SK1.xml.gz"]},
    {"id": "EPGSHARE_NL1", "label_pl": "NL - EPGShare NL1", "label_en": "NL - EPGShare NL1", "urls": ["https://epgshare01.online/epgshare01/epg_ripper_NL1.xml.gz"]},
    {"id": "POLISHTEAM_TV", "label_pl": "PL - PolishTeam TV (XMLTV)", "label_en": "PL - PolishTeam TV (XMLTV)", "urls": ["https://epg.polishteam.one/guide.xml.gz"]},
    {"id": "IPTV_EPG_PL", "label_pl": "PL - IPTV-EPG.org (XMLTV)", "label_en": "PL - IPTV-EPG.org (XMLTV)", "urls": ["https://iptv-epg.org/files/epg-pl.xml.gz"]},
    {"id": "EPGPW_LITE", "label_pl": "GLOBAL - EPG.PW lite", "label_en": "GLOBAL - EPG.PW lite", "urls": ["https://epg.pw/xmltv/epg_lite.xml.gz"]},
    {"id": "EPGPW_ALL", "label_pl": "GLOBAL - EPG.PW full (duży plik)", "label_en": "GLOBAL - EPG.PW full (large file)", "urls": ["https://epg.pw/xmltv/epg.xml.gz"]},
    {"id": "CUSTOM", "label_pl": "--- Własny URL XML/XML.GZ ---", "label_en": "--- Custom XML/XML.GZ URL ---", "urls": []},
]

SOURCE_MAP = dict((item["id"], item) for item in SOURCE_DEFINITIONS)


def source_choices(lang="pl"):
    key = "label_pl" if lang == "pl" else "label_en"
    return [(item["id"], item.get(key) or item.get("label_en") or item["id"]) for item in SOURCE_DEFINITIONS]
