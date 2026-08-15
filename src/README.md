# Simple IPTV EPG 3.0.0 build r1

AIO XMLTV + SAT EPG utility for Enigma2.

## Main features

- automatic IPTV service discovery from Enigma2 bouquets;
- XMLTV download with fallback sources;
- exact `tvg-id` / `epg-id` matching and conservative automatic name mapping;
- optional SAT → IPTV EPG cloning;
- direct import to Enigma2 `eEPGCache`;
- automatic import scheduler;
- source health test;
- diagnostics and persistent report;
- mapping cache tied to the actual XMLTV source and current bouquet signature;
- custom XML/XML.GZ URL;
- project QR and AIO IPTV PL identity.

## Controls

- **RED** – close;
- **GREEN** – import EPG;
- **YELLOW** – test selected source;
- **BLUE / MENU** – tools;
- **INFO** – project information and QR;
- **OK** – save settings.

## Files

- `/tmp/simpleiptvepg.log` – runtime log;
- `/etc/enigma2/simpleiptvepg_state.json` – last run state;
- `/etc/enigma2/simpleiptvepg_report.json` – last detailed report;
- `/etc/enigma2/simpleiptvepg_mapping.json` – mapping cache;
- `/etc/enigma2/simpleiptvepg_overrides.json` – optional manual overrides.

Manual override format:

```json
{
  "TVP1": "tvp1.pl",
  "TVN24": "tvn24.pl"
}
```

Keys can be normalized channel group names. Values must be existing XMLTV channel IDs.

## Project

AIO IPTV PL / Paweł Pawełek  
E-mail: aio-iptv@wp.pl  
Project website: https://olioli2013.github.io/aio-iptv-projekt/
