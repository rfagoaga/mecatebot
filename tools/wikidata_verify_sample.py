#!/usr/bin/env python3
"""CJ7: second check of journals that SPARQL did not find in Wikidata, on a random sample, with the search API.

For each sampled journal of not_found.csv (wikidata_journal_status.py):
  1. every ISSN: list=search srsearch=haswbstatement:P236=<issn>, then haswbstatement:P7363=<issn>
  2. the title: list=search srsearch="<title>" haswbstatement:P31=Q5633421|P31=Q737498|P31=Q1002697|P31=Q41298
     (scientific/academic journal, periodical, magazine) -> title candidates only (never treated as a match)
Raw responses + receipts are saved; rerun the same command to resume. Read only: no login, no edits.
Output: sample_check.csv, summary.json (share found by ISSN = how much SPARQL missed).
"""
from __future__ import annotations
import argparse, csv, hashlib, json, random, sys, time, urllib.parse, urllib.request
from collections import Counter
from pathlib import Path

API = 'https://www.wikidata.org/w/api.php'
TYPES = 'haswbstatement:P31=Q5633421|P31=Q737498|P31=Q1002697|P31=Q41298'


MAXLAG = '5'
def get(out: Path, name: str, params: dict, ua: str, pause: float):
    raw = out / 'raw' / f'{name}.json'
    if raw.exists(): return json.loads(raw.read_text(encoding='utf-8'))
    url = API + '?' + urllib.parse.urlencode({**params, 'format': 'json', 'maxlag': MAXLAG})
    for attempt in range(8):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': ua, 'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=60) as r: body = r.read(); status = r.status; ra = r.headers.get('Retry-After')
            d = json.loads(body)
            if d.get('error', {}).get('code') == 'maxlag':
                wait = max(int(ra or 5), 5 * (attempt + 1))
                print(f'  Wikidata is lagged ({d["error"].get("info", "")[:80]}); waiting {wait}s', flush=True)
                time.sleep(wait); continue
            if 'error' in d: print(f'  API error for {name}: {d["error"]}', flush=True)
            raw.write_bytes(body)
            (out / 'raw' / f'{name}.receipt.json').write_text(json.dumps({'url': url, 'status': status,
                'sha256': hashlib.sha256(body).hexdigest(), 'utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}))
            time.sleep(pause); return d
        except Exception as e:
            print(f'  {name}: {type(e).__name__}: {str(e)[:150]} (retry {attempt + 1}/8)', flush=True)
            if attempt == 7: raise SystemExit(f'{name}: {e}')
            time.sleep(15 * (attempt + 1))
    raise SystemExit(f'{name}: Wikidata stayed lagged; rerun later (progress is saved), or use --maxlag 10')


def hits(d):
    return [(x.get('title', ''), x.get('snippet', '')) for x in (d or {}).get('query', {}).get('search', [])]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--not-found', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--n', type=int, default=500, help='sample size; 0 = every journal of the file')
    ap.add_argument('--combined', action='store_true', help='one ISSN request per journal (all ISSNs, P236|P7363)')
    ap.add_argument('--seed', type=int, default=20261109)
    ap.add_argument('--mailto', required=True)
    ap.add_argument('--pause', type=float, default=1.0)
    ap.add_argument('--maxlag', default='5', help='Wikidata maxlag (seconds); raise to 10 if the servers stay lagged')
    a = ap.parse_args()
    global MAXLAG; MAXLAG = a.maxlag
    ua = f'CJ7-wikidata-journal-check/1.0 (Citational Justice research; read-only; mailto:{a.mailto})'
    (a.out / 'raw').mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(a.not_found.open(encoding='utf-8')))
    sample = rows if a.n == 0 else random.Random(a.seed).sample(rows, min(a.n, len(rows)))
    res = []
    print(f'{len(sample)} journals sampled from {len(rows)}; first request...', flush=True)
    for k, r in enumerate(sample, 1):
        iss = [x.strip() for x in r['issns'].split('|') if x.strip()]
        found = set()
        if a.combined:   # one request per journal: all ISSNs, P236 or P7363 (pipe = OR in haswbstatement)
            expr = '|'.join(f'{p}={i}' for i in iss for p in ('P236', 'P7363'))
            found = {t for t, _ in hits(get(a.out, f'issns-{r["journal_id"]}', {'action': 'query', 'list': 'search',
                     'srsearch': f'haswbstatement:{expr}', 'srlimit': 10}, ua, a.pause))}
        else:
            for i in iss:
                for p in ('P236', 'P7363'):
                    found |= {t for t, _ in hits(get(a.out, f'{p}-{i}', {'action': 'query', 'list': 'search',
                              'srsearch': f'haswbstatement:{p}={i}', 'srlimit': 10}, ua, a.pause))}
        t = (r['title'] or '').replace('"', ' ').strip()[:200]
        tc = []
        if t:
            h = hashlib.sha1(t.encode()).hexdigest()[:12]
            tc = [x for x, _ in hits(get(a.out, f'title-{h}', {'action': 'query', 'list': 'search',
                  'srsearch': f'"{t}" {TYPES}', 'srlimit': 5}, ua, a.pause))]
        res.append({'journal_id': r['journal_id'], 'title': r['title'], 'issns': r['issns'], 'country_code': r['country_code'],
                    'region': r['region'], 'found_by_issn': ';'.join(sorted(found)), 'title_candidates': ';'.join(tc),
                    'verdict': ('exists_by_issn' if found else 'single_title_candidate' if len(tc) == 1
                                else 'generic_title_candidates' if tc else 'absent')})
        if k % (10 if len(sample) <= 1000 else 500) == 0: print(f'{k}/{len(sample)}', flush=True)
    with (a.out / 'sample_check.csv').open('w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(res[0])); w.writeheader(); w.writerows(res)
    n = len(res); fi = sum(bool(x['found_by_issn']) for x in res); tc = sum(bool(x['title_candidates']) and not x['found_by_issn'] for x in res)
    summary = {'generated_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'not_found_total': len(rows),
               'sample': n, 'seed': a.seed if a.n else 'all', 'combined_issn_query': a.combined, 'found_by_issn_via_search_api': fi, 'pct_found_by_issn': round(100 * fi / n, 1),
               'not_found_by_issn_but_title_candidate': tc, 'pct_title_candidate': round(100 * tc / n, 1),
               'still_absent': n - fi - tc, 'pct_still_absent': round(100 * (n - fi - tc) / n, 1),
               'note': 'found_by_issn = SPARQL missed it (lag or format). title_candidate = an item with the same title and '
                       'a journal type but none of our ISSNs: review (could be the same journal without ISSN in Wikidata). '
                       'Read-only; no edits.'}
    summary['verdicts'] = dict(Counter(x['verdict'] for x in res))
    (a.out / 'summary.json').write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(summary, indent=1, ensure_ascii=False))


if __name__ == '__main__':
    main()
