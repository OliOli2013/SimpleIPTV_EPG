# -*- coding: utf-8 -*-
from __future__ import absolute_import, print_function

import difflib
import gzip
import xml.etree.ElementTree as ET

from .epgcore import compact_name, local_tag, name_variants, tokenize
from .logger import log_message


class AutoMapper(object):
    """Conservative XMLTV mapper. Ambiguous fuzzy matches are rejected."""

    def __init__(self, log_callback=None, sensitivity="balanced", overrides=None):
        self.log_callback = log_callback
        self.sensitivity = sensitivity or "balanced"
        self.overrides = overrides if isinstance(overrides, dict) else {}

    def _log(self, message):
        log_message(message)
        if self.log_callback:
            try:
                self.log_callback(message)
            except Exception:
                pass

    def _threshold(self):
        if self.sensitivity == "strict":
            return 0.96
        if self.sensitivity == "flexible":
            return 0.87
        return 0.91

    def _group_services(self, services):
        groups = {}
        for service in services or []:
            ref = service.get("full_ref")
            candidates = [item for item in (service.get("candidates") or []) if item]
            primary = service.get("norm") or (candidates[0] if candidates else "")
            if not primary:
                continue
            bucket = groups.setdefault(primary, {
                "refs": [], "candidates": set(), "tokens": set(), "id_hints": set(),
                "name": service.get("name", ""), "primary": primary,
            })
            if ref and ref not in bucket["refs"]:
                bucket["refs"].append(ref)
            bucket["candidates"].update(candidates)
            bucket["tokens"].update(service.get("tokens") or [])
            bucket["id_hints"].update(service.get("id_hints") or [])
            for variant in name_variants(service.get("name", "")):
                value = compact_name(variant)
                if value:
                    bucket["candidates"].add(value)
        return groups

    def _build_xml_index(self, xml_path):
        exact_index = {}
        token_index = {}
        id_index = {}
        entries = {}
        opener = gzip.open if str(xml_path).lower().endswith(".gz") else open
        with opener(xml_path, "rb") as handle:
            context = ET.iterparse(handle, events=("end",))
            for _event, elem in context:
                tag = local_tag(elem.tag)
                if tag == "channel":
                    xml_id = elem.get("id") or ""
                    if not xml_id:
                        elem.clear()
                        continue
                    id_index[xml_id] = xml_id
                    id_index[xml_id.lower()] = xml_id
                    names = [xml_id]
                    for child in list(elem):
                        if local_tag(child.tag) == "display-name" and child.text:
                            names.append(child.text)
                    compacts = set()
                    tokens = set()
                    for raw_name in names:
                        compact = compact_name(raw_name)
                        if compact:
                            compacts.add(compact)
                            exact_index.setdefault(compact, set()).add(xml_id)
                        for token in tokenize(raw_name):
                            tokens.add(token)
                            token_index.setdefault(token, set()).add(xml_id)
                    entries[xml_id] = {"compacts": compacts, "tokens": tokens}
                    elem.clear()
                elif tag == "programme":
                    # XMLTV places channels before programmes. Stop after channel index is built.
                    break
        return exact_index, token_index, id_index, entries

    def _candidate_xml_ids(self, group, exact_index, token_index, entries):
        exact_hits = []
        seen = set()
        for candidate in sorted(group.get("candidates", set()), key=lambda item: (-len(item), item)):
            for xml_id in exact_index.get(candidate, set()):
                if xml_id not in seen:
                    exact_hits.append(xml_id)
                    seen.add(xml_id)
        if exact_hits:
            return exact_hits[:12]
        pool = set()
        tokens = sorted(list(group.get("tokens", set())), key=lambda item: (-len(item), item))
        for token in tokens[:6]:
            pool.update(token_index.get(token, set()))
            if len(pool) >= 160:
                break
        if len(pool) > 180:
            prefix = (group.get("primary") or "")[:3]
            narrowed = []
            for xml_id in pool:
                if prefix and any(item.startswith(prefix) for item in entries.get(xml_id, {}).get("compacts", set())):
                    narrowed.append(xml_id)
            if narrowed:
                pool = set(narrowed[:180])
        return list(pool)[:180]

    def _score(self, group, entry):
        group_compacts = list(group.get("candidates", set()))[:10]
        entry_compacts = list(entry.get("compacts", set()))[:10]
        group_tokens = set(group.get("tokens", set()))
        entry_tokens = set(entry.get("tokens", set()))
        overlap = len(group_tokens & entry_tokens)
        best = 0.0
        for left in group_compacts:
            for right in entry_compacts:
                if left == right:
                    return 1.0
                if left.startswith(right) or right.startswith(left):
                    best = max(best, 0.965)
                elif left in right or right in left:
                    best = max(best, 0.935)
                else:
                    best = max(best, difflib.SequenceMatcher(None, left, right).ratio())
        if overlap:
            coverage = float(overlap) / float(max(len(group_tokens), 1))
            best = max(best, 0.53 + (0.16 * min(overlap, 3)) + (0.12 * coverage))
        missing = len(group_tokens - entry_tokens)
        if missing >= 2:
            best -= min(0.20, 0.06 * missing)
        return max(best, 0.0)

    def generate_mapping(self, services, xml_path):
        groups = self._group_services(services)
        exact_index, token_index, id_index, entries = self._build_xml_index(xml_path)
        mapping = {}
        used_xml = {}
        unmatched = []
        ambiguous = []
        exact_count = 0
        fuzzy_count = 0
        override_count = 0
        total = len(groups)
        threshold = self._threshold()

        for index, (group_key, group) in enumerate(sorted(groups.items())):
            chosen = None
            reason = ""

            # User override: normalized group name -> XMLTV id.
            override = self.overrides.get(group_key) or self.overrides.get(group.get("name", ""))
            if override and override in entries:
                chosen = override
                reason = "override"
                override_count += 1

            # Direct tvg-id / epg_id / xmltv hint wins if the ID exists.
            if not chosen:
                for hint in group.get("id_hints", set()):
                    hit = id_index.get(hint) or id_index.get(str(hint).lower())
                    if hit:
                        chosen = hit
                        reason = "id"
                        exact_count += 1
                        break

            options = []
            if not chosen:
                for xml_id in self._candidate_xml_ids(group, exact_index, token_index, entries):
                    entry = entries.get(xml_id)
                    if not entry:
                        continue
                    score = self._score(group, entry)
                    if score >= threshold:
                        options.append((score, xml_id))
                options.sort(key=lambda item: (-item[0], item[1]))
                if options:
                    top_score, top_id = options[0]
                    second_score = options[1][0] if len(options) > 1 else 0.0
                    exactish = top_score >= 0.985
                    # Reject fuzzy ties; a wrong EPG is worse than no EPG.
                    if exactish or second_score == 0.0 or (top_score - second_score) >= 0.025:
                        owner = used_xml.get(top_id)
                        if owner is None or owner == group_key:
                            chosen = top_id
                            reason = "exact" if exactish else "fuzzy"
                            if exactish:
                                exact_count += 1
                            else:
                                fuzzy_count += 1
                    else:
                        ambiguous.append({"name": group.get("name", ""), "options": options[:3]})

            if chosen:
                used_xml.setdefault(chosen, group_key)
                refs = mapping.setdefault(chosen, [])
                for service_ref in group.get("refs", []):
                    if service_ref not in refs:
                        refs.append(service_ref)
            else:
                unmatched.append(group.get("name", ""))

            if self.log_callback and ((index + 1) % 50 == 0 or (index + 1) == total):
                self.log_callback("Mapowanie: %s/%s" % (index + 1, total))

        stats = {
            "groups": total,
            "matched_groups": total - len(unmatched),
            "xml_ids": len(mapping),
            "unmatched": len(unmatched),
            "ambiguous": len(ambiguous),
            "exact": exact_count,
            "fuzzy": fuzzy_count,
            "overrides": override_count,
            "unmatched_names": unmatched[:250],
            "ambiguous_items": ambiguous[:100],
        }
        self._log("Mapping summary: groups=%s matched=%s xml_ids=%s ambiguous=%s" % (
            total, stats["matched_groups"], len(mapping), len(ambiguous)))
        return mapping, stats
