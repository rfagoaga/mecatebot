#!/usr/bin/env python3
"""MecateBot — Wikidata uploader for reviewed edit plans (stage 1: completing journal items).

Operator: Romano1920. Policy: https://www.wikidata.org/wiki/Wikidata:Bots
Python 3 standard library only.

SAFETY BY DEFAULT
  * Dry run unless --live is given: nothing is written, the final payload of every edit is shown and logged.
  * Item-space edits require an open approval request (or approval). --sandbox sends the same edits to the
    Wikidata sandbox items instead (no approval needed there).
  * Stop switch: create a file named STOP in the --out folder and the bot halts before the next edit.

WHAT EACH EDIT GOES THROUGH (double verification, check 2 = live)
  1. wbgetentities on the target right before editing: it must exist, not be a redirect or deleted, be a
     journal (P31 among the accepted journal types) and still carry at least one of the ISSNs it was matched
     on (plan field match_issns). Otherwise the record goes to review.
  2. Every value item (e.g. P495 country) is fetched too: must exist, not be a redirect.
  3. Recompute against the live item: a statement whose value is already there is not duplicated; if our
     source is missing on it, our reference is ADDED to that statement (policy: a new source for an existing
     statement is added as a new reference). Conflicting values are never touched.
  4. ONE wbeditentity call per item, with baserevid = lastrevid, bot=1 (once flagged), assert, maxlag=5,
     a descriptive summary. Nothing is removed or replaced.
  5. On a timeout/uncertain response the bot stops; it never repeats an edit blindly.
Every edit (or skip) is logged with the revision ID: <out>/edit_log.jsonl and edit_log.csv.

Usage
  python3 mecatebot.py --plans item_plans.jsonl --out RUN_DIR                 # dry run
  python3 mecatebot.py --plans item_plans.jsonl --out RUN_DIR --sandbox --live --limit 5
  python3 mecatebot.py --plans item_plans.jsonl --out RUN_DIR --live --limit 25 --assert user   # trial
The bot password (Special:BotPasswords of MecateBot) is asked interactively and never stored.
"""
from __future__ import annotations
import argparse, csv, getpass, http.cookiejar, json, sys, time, urllib.parse, urllib.request
from pathlib import Path

API = 'https://www.wikidata.org/w/api.php'
UA = 'MecateBot/0.1 (https://www.wikidata.org/wiki/User:MecateBot; operator User:Romano1920) Python-urllib'
JOURNAL_TYPES = {'Q5633421', 'Q737498', 'Q1002697', 'Q41298', 'Q2217301', 'Q1700470'}  # scientific/academic journal, periodical, magazine...
SANDBOX_ITEMS = ['Q4115189', 'Q13406268', 'Q15397819']  # Wikidata Sandbox items


class Api:
    def __init__(self, maxlag='5', assert_='user', bot_flag=False):
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))
        self.maxlag, self.assert_, self.bot_flag, self.token = maxlag, assert_, bot_flag, None

    def call(self, params, post=False, timeout=60):
        params = {**params, 'format': 'json', 'formatversion': '2'}
        for attempt in range(8):
            data = urllib.parse.urlencode(params).encode() if post else None
            url = API if post else API + '?' + urllib.parse.urlencode(params)
            req = urllib.request.Request(url, data=data, headers={'User-Agent': UA})
            with self.op.open(req, timeout=timeout) as r:
                d = json.loads(r.read()); ra = r.headers.get('Retry-After')
            if d.get('error', {}).get('code') == 'maxlag':
                wait = max(int(ra or 5), 5 * (attempt + 1)); print(f'  lag: waiting {wait}s', flush=True); time.sleep(wait); continue
            return d
        raise SystemExit('Wikidata stayed lagged; stopped (rerun later).')

    def login(self, user, password):
        t = self.call({'action': 'query', 'meta': 'tokens', 'type': 'login'})['query']['tokens']['logintoken']
        r = self.call({'action': 'login', 'lgname': user, 'lgpassword': password, 'lgtoken': t}, post=True)
        if r.get('login', {}).get('result') != 'Success': raise SystemExit(f'Login failed: {r.get("login")}')
        self.token = self.call({'action': 'query', 'meta': 'tokens'})['query']['tokens']['csrftoken']
        rights = self.call({'action': 'query', 'meta': 'userinfo', 'uiprop': 'rights|groups'})['query']['userinfo']
        self.bot_flag = 'bot' in rights.get('groups', [])
        return rights

    def entities(self, ids):
        d = self.call({'action': 'wbgetentities', 'ids': '|'.join(ids), 'props': 'info|claims|labels', 'redirects': 'no'})
        return d.get('entities', {})

    def edit(self, qid, data, baserevid, summary):
        p = {'action': 'wbeditentity', 'id': qid, 'data': json.dumps(data, ensure_ascii=False), 'token': self.token,
             'baserevid': str(baserevid), 'summary': summary, 'maxlag': self.maxlag, 'assert': self.assert_}
        if self.bot_flag: p['bot'] = '1'
        return self.call(p, post=True, timeout=120)


def values(ent, prop):
    out = []
    for c in ent.get('claims', {}).get(prop, []):
        dv = c.get('mainsnak', {}).get('datavalue', {}).get('value')
        out.append((c, dv['id'] if isinstance(dv, dict) and 'id' in dv else dv))
    return out


def same_ref(r1, r2):
    g = lambda r: {k: json.dumps([s.get('datavalue', {}).get('value') for s in v], sort_keys=True)
                   for k, v in r.get('snaks', {}).items() if k != 'P813'}
    return g(r1) == g(r2)


def recompute(ent, claims):
    """Return (claims to send, notes). Skips duplicates, adds missing references, never touches conflicts."""
    send, notes = [], []
    for c in claims:
        prop = c['mainsnak']['property']; dv = c['mainsnak']['datavalue']['value']
        val = dv['id'] if isinstance(dv, dict) and 'id' in dv else dv
        existing = [x for x, v in values(ent, prop) if v == val]
        if not existing:
            if prop == 'P495' and values(ent, 'P495'):
                notes.append(f'{prop} conflict: item has another country, held'); continue
            send.append(c); notes.append(f'add {prop}={val}'); continue
        ex = existing[0]
        if any(same_ref(r, c['references'][0]) for r in ex.get('references', [])):
            notes.append(f'{prop}={val} already present with our source'); continue
        upd = {'id': ex['id'], 'mainsnak': ex['mainsnak'], 'type': 'statement', 'rank': ex.get('rank', 'normal'),
               'references': ex.get('references', []) + c['references']}
        if ex.get('qualifiers'): upd['qualifiers'] = ex['qualifiers']; upd['qualifiers-order'] = ex.get('qualifiers-order', [])
        send.append(upd); notes.append(f'{prop}={val} exists: add our reference')
    return send, notes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--plans', type=Path, required=True, help='item_plans.jsonl (wikidata_complete_journals.py)')
    ap.add_argument('--out', type=Path, required=True, help='run folder (logs; put a file named STOP here to halt)')
    ap.add_argument('--live', action='store_true', help='actually edit (default: dry run)')
    ap.add_argument('--sandbox', action='store_true', help='send the edits to the Wikidata sandbox items instead')
    ap.add_argument('--limit', type=int, default=25)
    ap.add_argument('--per-minute', type=float, default=10, help='maximum edits per minute (policy requirement)')
    ap.add_argument('--assert', dest='assert_', choices=['user', 'bot'], default='user',
                    help="'user' before the bot flag is granted, 'bot' after")
    ap.add_argument('--user', default='MecateBot@mecate', help='bot-password login name')
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    done = set()
    logf = a.out / 'edit_log.jsonl'
    if logf.exists():
        for line in logf.open(encoding='utf-8'):
            x = json.loads(line)
            if x.get('result') == 'edited': done.add(x['plan_qid'])
    plans = [json.loads(l) for l in a.plans.open(encoding='utf-8')]
    todo = [p for p in plans if p['qid'] not in done][:a.limit]
    api = Api(assert_=a.assert_)
    if a.live:
        pw = getpass.getpass(f'Bot password for {a.user}: ')
        info = api.login(a.user, pw)
        print(f"Logged in as {info.get('name')} (groups: {', '.join(info.get('groups', []))}; bot flag: {api.bot_flag})")
        if a.assert_ == 'bot' and not api.bot_flag: raise SystemExit('--assert bot but the account has no bot flag yet')
    gap = 60.0 / a.per_minute; last = 0.0; n_edit = 0
    print(f"{'LIVE' if a.live else 'DRY RUN'}{' (sandbox)' if a.sandbox else ''}: {len(todo)} plans, <= {a.per_minute}/min")
    with logf.open('a', encoding='utf-8') as log:
        for k, p in enumerate(todo, 1):
            if (a.out / 'STOP').exists(): print('STOP file found: halting.'); break
            rec = {'utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'plan_qid': p['qid'], 'journal_id': p.get('journal_id'),
                   'title': p.get('title'), 'live': a.live, 'sandbox': a.sandbox}
            target = SANDBOX_ITEMS[(k - 1) % len(SANDBOX_ITEMS)] if a.sandbox else p['qid']
            ent = api.entities([target]).get(target, {})
            problem = None
            if 'missing' in ent or not ent: problem = 'target missing/deleted'
            elif ent.get('id') != target: problem = f'target redirects to {ent.get("id")}'
            elif not a.sandbox:
                if not ({v for _, v in values(ent, 'P31')} & JOURNAL_TYPES): problem = 'target is not a journal (P31)'
                elif p.get('match_issns') and not (set(p['match_issns']) & {v for _, v in values(ent, 'P236')}):
                    problem = 'target no longer carries the matched ISSN'
            vals = sorted({c['mainsnak']['datavalue']['value']['id'] for c in p['data']['claims']
                           if isinstance(c['mainsnak']['datavalue']['value'], dict)})
            if not problem and vals:
                ve = api.entities(vals)
                bad = [v for v in vals if 'missing' in ve.get(v, {'missing': 1}) or ve[v].get('id') != v]
                if bad: problem = f'linked item missing/redirect: {bad}'
            if problem:
                rec.update(result='review', reason=problem); log.write(json.dumps(rec) + '\n'); log.flush()
                print(f'{k:>4} {p["qid"]} REVIEW: {problem}'); continue
            send, notes = recompute(ent if not a.sandbox else {'claims': {}}, p['data']['claims'])
            rec['notes'] = notes
            if not send:
                rec.update(result='nothing_to_do'); log.write(json.dumps(rec) + '\n'); log.flush()
                print(f'{k:>4} {p["qid"]} nothing to do ({"; ".join(notes)})'); continue
            props = sorted({c['mainsnak']['property'] for c in send})
            summary = (f'MecateBot stage 1 (journals): {", ".join(props)} with source references, CJ7 register'
                       f'{" [sandbox test for " + p["qid"] + "]" if a.sandbox else ""}')
            rec.update(target=target, payload={'claims': send}, summary=summary, baserevid=ent.get('lastrevid'))
            if not a.live:
                rec['result'] = 'dry_run'; log.write(json.dumps(rec, ensure_ascii=False) + '\n'); log.flush()
                print(f'{k:>4} {p["qid"]} would edit {target}: {"; ".join(notes)}'); continue
            wait = gap - (time.time() - last)
            if wait > 0: time.sleep(wait)
            try:
                r = api.edit(target, {'claims': send}, ent.get('lastrevid'), summary)
            except Exception as e:
                rec.update(result='uncertain', reason=f'{type(e).__name__}: {e}'); log.write(json.dumps(rec) + '\n'); log.flush()
                raise SystemExit(f'Uncertain response for {target}; stopped. Check the item history before rerunning.')
            last = time.time()
            if 'error' in r:
                rec.update(result='error', reason=r['error']); log.write(json.dumps(rec) + '\n'); log.flush()
                print(f'{k:>4} {target} ERROR {r["error"].get("code")}: {r["error"].get("info", "")[:100]}')
                if r['error'].get('code') in ('editconflict', 'assertuserfailed', 'assertbotfailed', 'badtoken'): raise SystemExit('stopped')
                continue
            rev = r.get('entity', {}).get('lastrevid')
            rec.update(result='edited', revid=rev); log.write(json.dumps(rec, ensure_ascii=False) + '\n'); log.flush()
            n_edit += 1; print(f'{k:>4} {target} edited rev {rev}: {"; ".join(notes)}')
    rows = [json.loads(l) for l in logf.open(encoding='utf-8')]
    with (a.out / 'edit_log.csv').open('w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh); w.writerow(['utc', 'plan_qid', 'target', 'journal_id', 'title', 'result', 'revid', 'reason', 'notes'])
        for x in rows: w.writerow([x.get('utc'), x.get('plan_qid'), x.get('target', ''), x.get('journal_id'), x.get('title'),
                                   x.get('result'), x.get('revid', ''), x.get('reason', ''), '; '.join(x.get('notes', []))])
    print(f'done: {n_edit} edits this run; log: {logf}')


if __name__ == '__main__':
    main()
