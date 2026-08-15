# Simple IPTV EPG 3.0.0 r1

**Simple IPTV EPG** is an AIO XMLTV + SAT EPG utility for **Enigma2** receivers. Version **3.0.0 build r1** is a major architectural and user-interface rebuild focused on reliable IPTV EPG import, safer channel mapping, diagnostics and day-to-day usability.

## Main features

- automatic discovery of IPTV services from Enigma2 bouquets;
- XMLTV download with fallback sources and full XML/XML.GZ validation;
- exact `tvg-id`, `epg-id` and `xmltv-id` matching before conservative name matching;
- ambiguity rejection instead of guessing uncertain channel mappings;
- optional SAT → IPTV EPG cloning;
- direct event injection into Enigma2 `eEPGCache`;
- mapping cache tied to the effective XMLTV URL, bouquet signature and mapper sensitivity;
- automatic EPG scheduler: 6 / 12 / 24 / 48 hours;
- custom XML/XML.GZ source URL;
- source test, diagnostics, log viewer and cache cleanup tools;
- persistent state/report information under `/etc/enigma2`;
- adaptive AIO IPTV PL interface inspired by AIO Panel and other AIO projects;
- project information screen with QR code, author details and support QR;
- Python 2 / Python 3 compatible code paths.

## Controls

- **RED** – close;
- **GREEN** – import EPG;
- **YELLOW** – test selected source;
- **BLUE / MENU** – tools;
- **INFO** – project information and QR;
- **OK** – save settings.

## Installation

Connect to the receiver through SSH/Telnet and run:

```sh
wget -qO - https://raw.githubusercontent.com/OliOli2013/SimpleIPTV_EPG/main/installer.sh | /bin/sh
```

After installation restart the Enigma2 GUI.

## Runtime files

- `/tmp/simpleiptvepg.log` – runtime log;
- `/etc/enigma2/simpleiptvepg_state.json` – last-run state;
- `/etc/enigma2/simpleiptvepg_report.json` – detailed last report;
- `/etc/enigma2/simpleiptvepg_mapping.json` – mapping cache;
- `/etc/enigma2/simpleiptvepg_overrides.json` – optional manual overrides.

Example manual override:

```json
{
  "TVP1": "tvp1.pl",
  "TVN24": "tvn24.pl"
}
```

## 3.0.0 r1 hotfix

Build **r1** fixes GUI layering on Enigma2 skins/images where static `eLabel` backgrounds covered dynamic widgets. Explicit `zPosition` values were added to all plugin screens, restoring visibility of titles, configuration rows, status text, key captions, logos and QR codes.

The upstream plugin version remains **3.0.0**. The package/build revision is **r1**.

## Project

**AIO IPTV PL**  
**Author:** Paweł Pawełek  
**E-mail:** aio-iptv@wp.pl  
**Website:** https://olioli2013.github.io/aio-iptv-projekt/
