# -*- coding: utf-8 -*-
import difflib
import gzip
import xml.etree.cElementTree as ET

from .epgcore import compact_name, log_message, name_variants, tokenize


class AutoMapper(object):
    def __init__(self, log_callback=None):
        self.log_callback = log_callback

    def _log(self, message):
        log_message(message)
        if self.log_callback:
            try:
                self.log_callback(message)
            except Exception:
                pass

    def _group_services(self, services):
        groups = {}
        for service in services:
            ref = service.get("full_ref")
            candidates = [candidate for candidate in (service.get("candidates") or []) if candidate]
            primary = service.get("norm") or (candidates[0] if candidates else "")
            if not primary:
                continue
            bucket = groups.setdefault(primary, {
                "refs": [],
                "candidates": set(),
                "tokens": set(),
                "name": service.get("name", ""),
                "primary": primary,
            })
            if ref and ref not in bucket["refs"]:
                bucket["refs"].append(ref)
            for candidate in candidates:
                bucket["candidates"].add(candidate)
            for variant in name_variants(service.get("name", "")):
                compact = variant.replace(" ", "")
                if compact:
                    bucket["candidates"].add(compact)
            for token in tokenize(service.get("name", "")):
                bucket["tokens"].add(token)
        return groups

    def _build_xml_index(self, xml_path):
        exact_index = {}
        token_index = {}
        entries = {}
        opener = gzip.open if str(xml_path).lower().endswith(".gz") else open
        with opener(xml_path, "rb") as handle:
            context = ET.iterparse(handle, events=("end",))
            for _event, elem in context:
                if elem.tag == "channel":
                    xml_id = elem.get("id") or ""
                    names = [xml_id]
                    for child in elem:
                        if child.tag == "display-name" and child.text:
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
                    if xml_id:
                        entries[xml_id] = {
                            "compacts": compacts,
                            "tokens": tokens,
                        }
                    elem.clear()
                elif elem.tag == "programme":
                    break
        return exact_index, token_index, entries

    def _candidate_xml_ids(self, group, exact_index, token_index, entries):
        exact_hits = []
        seen = set()
        for candidate in sorted(group.get("candidates", set()), key=lambda item: (-len(item), item)):
            for xml_id in exact_index.get(candidate, set()):
                if xml_id not in seen:
                    exact_hits.append(xml_id)
                    seen.add(xml_id)
        if exact_hits:
            return exact_hits[:8]

        pool = set()
        sorted_tokens = sorted(list(group.get("tokens", set())), key=lambda item: (-len(item), item))
        for token in sorted_tokens[:5]:
            pool.update(token_index.get(token, set()))
            if len(pool) >= 96:
                break
        if len(pool) > 128:
            prefix = (group.get("primary") or "")[:3]
            filtered = [xml_id for xml_id in pool if prefix and any(compact.startswith(prefix) for compact in entries.get(xml_id, {}).get("compacts", set()))]
            pool = set(filtered[:128]) if filtered else set(list(pool)[:128])
        return list(pool)[:128]

    def _score(self, group, entry):
        group_compacts = [candidate for candidate in group.get("candidates", set()) if candidate]
        entry_compacts = list(entry.get("compacts", set()))
        group_tokens = set(group.get("tokens", set()))
        entry_tokens = set(entry.get("tokens", set()))
        overlap = len(group_tokens & entry_tokens)
        best = 0.0

        for group_compact in group_compacts[:8]:
            for xml_compact in entry_compacts[:8]:
                if group_compact == xml_compact:
                    return 1.0
                if group_compact.startswith(xml_compact) or xml_compact.startswith(group_compact):
                    best = max(best, 0.97)
                elif group_compact in xml_compact or xml_compact in group_compact:
                    best = max(best, 0.94)
                else:
                    ratio = difflib.SequenceMatcher(None, group_compact, xml_compact).ratio()
                    if ratio > best:
                        best = ratio

        if overlap:
            coverage = float(overlap) / float(max(len(group_tokens), 1))
            best = max(best, 0.52 + (0.18 * min(overlap, 3)) + (0.12 * coverage))

        if group_tokens and entry_tokens:
            missing = len(group_tokens - entry_tokens)
            if missing >= 2:
                best -= 0.08 * missing
        return max(best, 0.0)

    def _allow_shared_xml(self, existing_group, new_group):
        left = existing_group.get("primary", "")
        right = new_group.get("primary", "")
        if left == right:
            return True
        left_tokens = set(existing_group.get("tokens", set()))
        right_tokens = set(new_group.get("tokens", set()))
        overlap = len(left_tokens & right_tokens)
        if overlap >= max(2, min(len(left_tokens), len(right_tokens))):
            return True
        ratio = difflib.SequenceMatcher(None, left, right).ratio()
        return ratio >= 0.96

    def generate_mapping(self, services, xml_path):
        groups = self._group_services(services)
        exact_index, token_index, entries = self._build_xml_index(xml_path)
        mapping = {}
        xml_usage = {}
        total = len(groups)
        matched = 0

        for index, (group_key, group) in enumerate(sorted(groups.items())):
            best_options = []
            candidates = self._candidate_xml_ids(group, exact_index, token_index, entries)
            for xml_id in candidates:
                entry = entries.get(xml_id)
                if not entry:
                    continue
                score = self._score(group, entry)
                if score >= 0.90:
                    best_options.append((score, xml_id))
            best_options.sort(key=lambda item: (-item[0], item[1]))

            chosen_xml = None
            for score, xml_id in best_options:
                owner = xml_usage.get(xml_id)
                if owner and not self._allow_shared_xml(owner, group):
                    continue
                # very fuzzy matches require strong token overlap
                overlap = len(set(group.get("tokens", set())) & set(entries.get(xml_id, {}).get("tokens", set())))
                if score < 0.97 and overlap == 0:
                    continue
                chosen_xml = xml_id
                xml_usage.setdefault(xml_id, group)
                break

            if chosen_xml:
                refs = mapping.setdefault(chosen_xml, [])
                for service_ref in group.get("refs", []):
                    if service_ref not in refs:
                        refs.append(service_ref)
                matched += 1

            if self.log_callback and ((index + 1) % 50 == 0 or (index + 1) == total):
                self.log_callback("Mapowanie grup: %s/%s" % (index + 1, total))

        self._log("Mapping summary: groups=%s matched=%s xml_ids=%s" % (total, matched, len(mapping)))
        return mapping, {"groups": total, "matched_groups": matched, "xml_ids": len(mapping)}
