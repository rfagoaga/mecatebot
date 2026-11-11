#!/usr/bin/env python3
"""CJ7: edit plans to COMPLETE existing Wikidata journal items (missing ISSN P236, missing country of origin P495).
Never creates items, never removes or replaces anything, never edits Wikidata itself (offline plans only).

Two subcommands:
  fetch-countries  (network, read-only, once): ISO 3166-1 alpha-2 -> country item, from WDQS (P297), saved as JSON.
  plan             (offline): for journals with wikidata_status = exists_incomplete (wikidata_journal_status.py):
    * P236 for each of our ISSNs missing on the item, only with a citable source that lists that ISSN for a title
      matching the item: Crossref (issn_stats.csv.gz of the March 2026 public data file) or an observation whose
      source is mapped in --sources (DOAJ, OpenAlex, ... with a QID). Title mismatch (e.g. a later title of the
      journal) -> review, never proposed.
    * P495 when our country is anchored and an accepted claim with that same country comes from a mapped source.
    Every statement carries a reference: P248 stated in <source QID>, P854 reference URL when the source has one,
    P813 retrieved <date>.
Outputs (--out, new dir):
  item_plans.jsonl     one grouped wbeditentity template per item (claims + references; executable=false):
                       the future uploader must re-fetch the item, recompute, and send ONE edit per item.
  single_statement.qs  QuickStatements V1 lines ONLY for items receiving exactly one statement (one line = one edit);
                       items with two statements are only in item_plans.jsonl (grouped upload).
  review.csv           statements held back and why; sources_needed.csv: unmapped sources that would unlock more.
  summary.json
Rules: WIKIDATA_editing_rules_2026-11-09 (one edit per item, references, no deletions, conflated items excluded).
"""
from __future__ import annotations
import argparse, csv, gzip, html, json, re, sys, time, unicodedata, urllib.parse, urllib.request
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(sys.maxsize)
RX = re.compile(r'\d{4}-\d{3}[\dX]')
DEFAULT_SOURCES = {   # regex on observation source name -> reference. QIDs verified in wdlib.py (Crossref, OpenAlex) / DOAJ.
    'crossref': {'qid': 'Q5188229', 'label': 'Crossref', 'url': 'https://api.crossref.org/journals/{issn}'},
    'doaj': {'qid': 'Q1227538', 'label': 'Directory of Open Access Journals', 'url': 'https://doaj.org/toc/{issn}'},
    'openalex': {'qid': 'Q107507571', 'label': 'OpenAlex', 'url': 'https://api.openalex.org/sources/issn:{issn}'},
}


def fold(s):
    s = unicodedata.normalize('NFKD', html.unescape(s or ''))
    s = ''.join(c for c in s if not unicodedata.combining(c)).casefold()
    s = re.sub(r'[^\w]+', ' ', s).replace(' and ', ' ')
    s = re.sub(r'^(the|la|le|les|el|los|las|il|der|die|das)\s+', '', s.strip())
    return ' '.join(s.split())


def same_title(a, b):
    a, b = fold(a), fold(b)
    if not a or not b: return False
    if a == b or (min(len(a), len(b)) >= 8 and (a in b or b in a)): return True
    ta, tb = set(a.split()), set(b.split())
    return len(ta & tb) / len(ta | tb) >= 0.7


def snak(prop, dv, dtype):
    return {'snaktype': 'value', 'property': prop, 'datavalue': dv, 'datatype': dtype}


def item_dv(q): return {'value': {'entity-type': 'item', 'numeric-id': int(q[1:]), 'id': q}, 'type': 'wikibase-entityid'}


def reference(src, issn, today):
    snaks = {'P248': [snak('P248', item_dv(src['qid']), 'wikibase-item')],
             'P813': [snak('P813', {'value': {'time': f'+{today}T00:00:00Z', 'timezone': 0, 'before': 0, 'after': 0,
                                              'precision': 11, 'calendarmodel': 'http://www.wikidata.org/entity/Q1985727'},
                                    'type': 'time'}, 'time')]}
    order = ['P248']
    if src.get('url'):
        snaks['P854'] = [snak('P854', {'value': src['url'].format(issn=issn), 'type': 'string'}, 'url')]; order.append('P854')
    order.append('P813')
    return {'snaks': snaks, 'snaks-order': order}


def qs_ref(src, issn, today):
    s = f'|S248|{src["qid"]}'
    if src.get('url'): s += f'|S854|"{src["url"].format(issn=issn)}"'
    return s + f'|S813|+{today}T00:00:00Z/11'


def cmd_fetch_countries(a):
    q = ('SELECT ?item ?iso (COUNT(?sl) AS ?n) WHERE { ?item wdt:P297 ?iso . ?item wdt:P31 ?t . '
         'FILTER NOT EXISTS { ?item wdt:P576 ?end } OPTIONAL { ?sl schema:about ?item } } GROUP BY ?item ?iso')
    req = urllib.request.Request('https://query.wikidata.org/sparql', data=urllib.parse.urlencode({'query': q}).encode(),
                                 headers={'User-Agent': f'CJ7-wikidata-complete/1.0 (read-only; mailto:{a.mailto})',
                                          'Accept': 'application/sparql-results+json'})
    with urllib.request.urlopen(req, timeout=180) as r: body = r.read()
    best = {}
    for b in json.loads(body)['results']['bindings']:
        iso = b['iso']['value'].upper(); qid = b['item']['value'].rsplit('/', 1)[-1]; n = int(b['n']['value'])
        if iso not in best or n > best[iso][1]: best[iso] = (qid, n)
    a.out.write_text(json.dumps({k: v[0] for k, v in sorted(best.items())}, indent=1), encoding='utf-8')
    a.out.with_suffix('.raw.json').write_bytes(body)
    print(f'{len(best)} ISO codes -> {a.out}  (check a few: MX={best.get("MX")}, ID={best.get("ID")}, US={best.get("US")})')


def cmd_plan(a):
    if a.out.exists(): sys.exit(f'Output exists; choose a new path: {a.out}')
    today = time.strftime('%Y-%m-%d', time.gmtime())
    srcmap = dict(DEFAULT_SOURCES)
    if a.sources: srcmap.update({k: v for k, v in json.loads(a.sources.read_text(encoding='utf-8')).items() if v.get('qid')})
    srx = [(re.compile(k, re.I), v) for k, v in srcmap.items() if k != 'crossref']
    def map_src(name):
        for rx, v in srx:
            if rx.search(name): return v
        return None
    cqid = json.loads(a.country_qids.read_text(encoding='utf-8'))
    status = [r for r in csv.DictReader(a.status.open(encoding='utf-8')) if r['wikidata_status'] == 'exists_incomplete']
    reg = {r['journal_id']: r for r in csv.DictReader(a.register.open(encoding='utf-8'))}
    want = defaultdict(set)    # (disc) -> cluster ids
    j_of = {}
    for r in status:
        for c in (reg[r['journal_id']]['clusters'] or '').split(' | '):
            if ':' in c: d, cid = c.split(':', 1); want[d].add(cid); j_of[(d, cid)] = r['journal_id']
    obs = defaultdict(list)    # journal_id -> observations
    for d, cids in want.items():
        f = Path(f'{a.prefix}-{d}') / 'universe_observations.jsonl'
        if not f.is_file(): sys.exit(f'missing {f}')
        with f.open(encoding='utf-8') as fh:
            for line in fh:
                if '"cluster_id"' not in line: continue
                o = json.loads(line)
                if o.get('cluster_id') in cids: obs[j_of[(d, o['cluster_id'])]].append(o)
    cr = {}
    with gzip.open(a.issn_stats, 'rt', encoding='utf-8', newline='') as fh:
        for x in csv.DictReader(fh): cr[x['issn']] = x['container_title']
    plans, qs_lines, review, need = [], [], [], Counter()
    for r in status:
        q = r['qids']; j = r['journal_id']; wdt = r['wd_titles']; claims = []; qsl = []
        for i in [x for x in r['issns_missing_in_wd'].split(';') if x]:
            src = None
            if i in cr and (same_title(cr[i], wdt) or same_title(cr[i], r['title'])) and same_title(r['title'], wdt):
                src = srcmap['crossref']
            else:
                for o in obs[j]:
                    if i in o['issns'] and not o['source'].endswith('wikidata'):
                        m = map_src(o['source'])
                        if m and any(same_title(t, wdt) for t in o['titles']): src = m; break
                        if not m: need[o['source']] += 1
            if src is None:
                why = 'title_differs_from_item (possible later/earlier title: separate item?)' if i in cr else 'no_citable_mapped_source'
                review.append([q, j, r['title'], wdt, 'P236', i, why]); continue
            claims.append({'mainsnak': snak('P236', {'value': i, 'type': 'string'}, 'external-id'), 'type': 'statement',
                           'rank': 'normal', 'references': [reference(src, i, today)]})
            qsl.append(f'{q}|P236|"{i}"' + qs_ref(src, i, today))
        if 'missing_P495' in r['note']:
            cc = r['country_code']; src = None
            if cc in cqid:
                for o in obs[j]:
                    for c in o['country_claims']:
                        if c['code'] == cc and c['basis'] not in ('openalex_country_code', 'wikidata_country_of_origin', 'portal_hint'):
                            m = map_src(c.get('source') or o['source'])
                            if m: src = m; iss = (o['issns'] or [r['issns'].split(' | ')[0]])[0]; break
                            need[f"{c['basis']} ({c.get('source') or o['source']})"] += 1
                    if src: break
            if src is None:
                review.append([q, j, r['title'], wdt, 'P495', cc, 'no_country_qid' if cc not in cqid else 'no_citable_mapped_source'])
            else:
                claims.append({'mainsnak': snak('P495', item_dv(cqid[cc]), 'wikibase-item'), 'type': 'statement',
                               'rank': 'normal', 'references': [reference(src, iss, today)]})
                qsl.append(f'{q}|P495|{cqid[cc]}' + qs_ref(src, iss, today))
        if claims:
            jiss = [x.strip() for x in r['issns'].split('|') if x.strip()]
            miss = {x for x in r['issns_missing_in_wd'].split(';') if x}
            plans.append({'qid': q, 'journal_id': j, 'title': r['title'], 'wd_title': wdt, 'executable': False,
                          'match_issns': [x for x in jiss if x not in miss],
                          'review_required': True, 'summary': 'Adding sourced journal identifiers/country (CJ7 register)',
                          'data': {'claims': claims}})
            if len(qsl) == 1: qs_lines.append(qsl[0])
    a.out.mkdir(parents=True)
    with (a.out / 'item_plans.jsonl').open('w', encoding='utf-8') as fh:
        for p in plans: fh.write(json.dumps(p, ensure_ascii=False) + '\n')
    (a.out / 'single_statement.qs').write_text('\n'.join(qs_lines) + ('\n' if qs_lines else ''), encoding='utf-8')
    with (a.out / 'review.csv').open('w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh); w.writerow(['qid', 'journal_id', 'title', 'wd_title', 'property', 'value', 'reason']); w.writerows(review)
    with (a.out / 'sources_needed.csv').open('w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh); w.writerow(['source_or_basis', 'statements_it_would_support']); w.writerows(need.most_common())
    pc = Counter(c['mainsnak']['property'] for p in plans for c in p['data']['claims'])
    summary = {'generated_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'incomplete_journals': len(status),
               'items_with_plan': len(plans), 'statements': dict(pc),
               'items_single_statement_qs': len(qs_lines), 'items_needing_grouped_upload': len(plans) - len(qs_lines),
               'held_for_review': dict(Counter(x[6] for x in review)),
               'sources_used': dict(Counter(ref['snaks']['P248'][0]['datavalue']['value']['id']
                                            for p in plans for c in p['data']['claims'] for ref in c['references'])),
               'retrieved_date': today, 'edits_made': 0}
    (a.out / 'summary.json').write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(summary, indent=1, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    f = sub.add_parser('fetch-countries'); f.add_argument('--out', type=Path, required=True); f.add_argument('--mailto', required=True)
    p = sub.add_parser('plan')
    p.add_argument('--status', type=Path, required=True, help='journal_wikidata_status.csv')
    p.add_argument('--register', type=Path, required=True)
    p.add_argument('--prefix', required=True, help='universe prefix of the register (e21)')
    p.add_argument('--issn-stats', type=Path, required=True)
    p.add_argument('--country-qids', type=Path, required=True)
    p.add_argument('--sources', type=Path, help='optional JSON {regex: {qid,label,url}} adding sources (QIDs checked by Chi)')
    p.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    cmd_fetch_countries(a) if a.cmd == 'fetch-countries' else cmd_plan(a)


if __name__ == '__main__':
    main()
