#!/usr/bin/env python3
"""CJ7: which journals of the register exist in Wikidata, and how. No network, no edits.

Inputs: register.csv (export_register.py) and extra_wikidata_issn.csv (harvest_group1_routes.py wikidata-issn over the
register's ISSNs; SPARQL on P236/P7363, raw responses kept in that folder).
Status per register journal with ISSN (journal_wikidata_status.csv):
  exists              one Wikidata item holds the journal's ISSNs; nothing we hold is missing there
  exists_incomplete   one item, but it lacks one of our ISSNs and/or P495 while our country is anchored
  country_conflict    one item whose P495 differs from our anchored country (review, never overwrite)
  multiple_items      two or more items carry the journal's ISSNs (duplicates in Wikidata, or title history)
  shared_item         the journal's item also carries ISSNs of other register records. Subtype:
                        same_title  -> very likely one journal split in our register (print/online not linked)
                        other_title -> possibly a wrongly merged Wikidata item (PoLAR / Polar Journal case) or a
                                       title change; review, never edit the item meanwhile
  not_found           no item with any of its ISSNs (SPARQL can lag: re-check before proposing creation)
Also writes shared_items.csv (one row per item covering several register records), not_found.csv and summary.json
(counts by status, country and region). Nothing is merged or edited.
"""
from __future__ import annotations
import argparse, csv, hashlib, html, json, re, sys, time, unicodedata
from collections import Counter, defaultdict
from pathlib import Path

RX = re.compile(r'\d{4}-\d{3}[\dX]')
csv.field_size_limit(sys.maxsize)


def fold(s):
    s = unicodedata.normalize('NFKD', html.unescape(s or ''))
    s = ''.join(c for c in s if not unicodedata.combining(c)).casefold()
    s = re.sub(r'^(the|la|le|les|el|los|las|il|der|die|das|o|a)\s+', '', re.sub(r'[^\w]+', ' ', s).strip())
    return ' '.join(s.split())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--register', type=Path, required=True)
    ap.add_argument('--wikidata', type=Path, required=True, help='extra_wikidata_issn.csv')
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    if a.out.exists(): sys.exit(f'Output exists; choose a new path: {a.out}')
    reg = [r for r in csv.DictReader(a.register.open(encoding='utf-8')) if r['issns']]
    jissn = {r['journal_id']: set(RX.findall(r['issns'].upper())) for r in reg}
    byid = {r['journal_id']: r for r in reg}
    issn2j = defaultdict(set)
    for j, s in jissn.items():
        for i in s: issn2j[i].add(j)
    wd = defaultdict(lambda: {'issns': set(), 'countries': set(), 'title': '', 'start': '', 'end': '', 'publisher': ''})
    for r in csv.DictReader(a.wikidata.open(encoding='utf-8')):
        w = wd[r['record_id']]; w['issns'].update(RX.findall((r['issn'] or '').upper()))
        if r['country']: w['countries'].add(r['country'])
        for k, src in (('title', 'title'), ('start', 'start_year'), ('end', 'end_year'), ('publisher', 'publisher')):
            w[k] = w[k] or r[src]
    q2j = {q: {j for i in w['issns'] for j in issn2j.get(i, ())} for q, w in wd.items()}
    j2q = defaultdict(set)
    for q, js in q2j.items():
        for j in js: j2q[j].add(q)
    a.out.mkdir(parents=True)
    rows, st = [], Counter()
    shared_rows = []
    for q, js in sorted(q2j.items()):
        if len(js) < 2: continue
        tl = {fold(byid[j]['title']) for j in js}
        sub = 'same_title' if len(tl) == 1 or fold(wd[q]['title']) in tl and len(tl) <= 2 and len({t[:12] for t in tl}) == 1 else 'other_title'
        shared_rows.append([q, wd[q]['title'], ';'.join(sorted(wd[q]['issns'])), sub, len(js),
                            ' || '.join(f"{j}: {byid[j]['title']}" for j in sorted(js))])
    shared_sub = {r[0]: r[3] for r in shared_rows}
    for r in reg:
        j = r['journal_id']; qs = sorted(j2q.get(j, ()), key=lambda x: int(x[1:]))
        cc, anch = r['country_code'], r['country_status'] == 'anchored'
        missing, wdc, note = set(), set(), ''
        if not qs: s = 'not_found'
        elif len(qs) > 1: s = 'multiple_items'
        elif qs[0] in shared_sub: s = 'shared_item'; note = shared_sub[qs[0]]
        else:
            w = wd[qs[0]]; missing = jissn[j] - w['issns']; wdc = w['countries']
            if anch and wdc and cc not in wdc: s = 'country_conflict'
            elif missing or (anch and not wdc): s = 'exists_incomplete'; note = ';'.join(
                (['missing_issn'] if missing else []) + (['missing_P495'] if anch and not wdc else []))
            else: s = 'exists'
        st[s] += 1
        rows.append({'journal_id': j, 'title': r['title'], 'issns': r['issns'], 'country_code': cc,
                     'country_status': r['country_status'], 'region': r['region'], 'disciplines': r['disciplines'],
                     'in_crossref': r['in_crossref'], 'deposits_references': r['deposits_references'],
                     'wikidata_status': s, 'note': note, 'qids': ';'.join(qs),
                     'wd_titles': ' || '.join(wd[q]['title'] for q in qs),
                     'wd_countries': ';'.join(sorted({c for q in qs for c in wd[q]['countries']})),
                     'issns_missing_in_wd': ';'.join(sorted(missing)), 'start_year': r['start_year'],
                     'end_year': r['end_year'], 'publishers': r['publishers']})
    cols = list(rows[0])
    for name, rs in (('journal_wikidata_status.csv', rows), ('not_found.csv', [x for x in rows if x['wikidata_status'] == 'not_found'])):
        with (a.out / name).open('w', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(rs)
    with (a.out / 'shared_items.csv').open('w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh); w.writerow(['qid', 'wd_title', 'wd_issns', 'subtype', 'register_records', 'records'])
        w.writerows(sorted(shared_rows, key=lambda x: (x[3], -x[4])))
    def tab(key):
        tot = Counter(x[key] or '?' for x in rows); nf = Counter(x[key] or '?' for x in rows if x['wikidata_status'] == 'not_found')
        return {k: {'journals': tot[k], 'not_found': nf[k], 'pct_not_found': round(100 * nf[k] / tot[k], 1)}
                for k, _ in tot.most_common()}
    summary = {'generated_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'register': str(a.register),
               'wikidata': str(a.wikidata), 'wikidata_sha256': hashlib.sha256(a.wikidata.read_bytes()).hexdigest(),
               'journals_with_issn': len(rows), 'wikidata_items_matched': len(wd), 'status': dict(st.most_common()),
               'shared_items': dict(Counter(x[3] for x in shared_rows)),
               'not_found_in_crossref': sum(1 for x in rows if x['wikidata_status'] == 'not_found' and x['in_crossref'] == '1'),
               'by_region': tab('region'), 'by_country': dict(list(tab('country_code').items())[:60]),
               'note': 'SPARQL (P236/P7363) can lag; not_found must be re-checked with the search API before any creation. '
                       'No edits, no merges.'}
    (a.out / 'summary.json').write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({k: v for k, v in summary.items() if k not in ('by_region', 'by_country')}, indent=1, ensure_ascii=False))
    print('regions (not found / journals):', {k: f"{v['not_found']}/{v['journals']}" for k, v in summary['by_region'].items()})


if __name__ == '__main__':
    main()
