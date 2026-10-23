"""ONE-OFF (22 Oct, his 'do whatever it takes'; 23 Oct: any epic via HIST_EPIC, e.g. USDCNH for the yuan research): download Capital.com MINUTE history (bid+ask OHLC + lastTradedVolume) as far back as
the API gives, for the oil buy-side volume research. Read-only market data; no orders. Saves data/oil_hist_min.csv.gz."""
import os, sys, time, gzip, json, datetime as dt, requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from feeds import Capital
EPIC = os.environ.get('HIST_EPIC', 'OIL_CRUDE'); YEARS = float(os.environ.get('HIST_YEARS', '3'))
cap = Capital(); cap.login()
T_START = time.time(); BUDGET = float(os.environ.get('HIST_BUDGET_MIN', '45')) * 60
TAG = 'oil' if EPIC == 'OIL_CRUDE' else EPIC.lower()          # oil keeps its old file names
try:                                                          # read-only: list matching markets so a wrong epic name is visible in the log
    q = requests.get(f'{cap.base}/api/v1/markets', headers=cap.h, timeout=30, params={'searchTerm': os.environ.get('HIST_SEARCH', EPIC)})
    print('markets search:', [(m.get('epic'), m.get('instrumentName')) for m in q.json().get('markets', [])][:15], flush=True)
except Exception as e: print('markets search failed', e, flush=True)
end = dt.datetime.utcnow().replace(second=0, microsecond=0); stop = end - dt.timedelta(days=365 * YEARS)
step = dt.timedelta(minutes=960); rows = {}; empty_run = 0; n_req = 0; first_err = None; t1 = end; keys_seen = None
while t1 > stop:
    t0 = t1 - step
    for attempt in range(3):
        r = requests.get(f'{cap.base}/api/v1/prices/{EPIC}', headers=cap.h, timeout=30,
                         params={'resolution': 'MINUTE', 'max': 1000, 'from': t0.strftime('%Y-%m-%dT%H:%M:%S'), 'to': t1.strftime('%Y-%m-%dT%H:%M:%S')})
        n_req += 1
        if r.status_code == 401: cap.login(); continue
        if r.status_code == 429: time.sleep(2); continue
        break
    if r.status_code == 200:
        ps = r.json().get('prices', [])
        if ps and keys_seen is None: keys_seen = sorted(ps[0].keys())
        for p in ps:
            g = lambda k, s: (p.get(k) or {}).get(s)
            rows[p['snapshotTimeUTC']] = (g('openPrice', 'bid'), g('highPrice', 'bid'), g('lowPrice', 'bid'), g('closePrice', 'bid'),
                                          g('openPrice', 'ask'), g('highPrice', 'ask'), g('lowPrice', 'ask'), g('closePrice', 'ask'), p.get('lastTradedVolume'))
        empty_run = 0 if ps else empty_run + 1
    else:
        empty_run += 1
        if first_err is None: first_err = (r.status_code, r.text[:200], t0.isoformat())
    if n_req % 100 == 0: print(f'progress {t0.isoformat()} rows {len(rows)} requests {n_req} last status {r.status_code}', flush=True)
    if time.time() - T_START > BUDGET: print('time budget reached - saving what we have', flush=True); break
    if empty_run >= 12: break            # ~8 days with nothing = history ends
    t1 = t0; time.sleep(0.12)
os.makedirs('data', exist_ok=True)
with gzip.open(f'data/{TAG}_hist_min.csv.gz', 'wt') as f:
    f.write('t_utc,bo,bh,bl,bc,ao,ah,al,ac,vol\n')
    for t in sorted(rows): f.write(t + ',' + ','.join('' if v is None else str(v) for v in rows[t]) + '\n')
ts = sorted(rows); vol = [v[8] for v in rows.values() if v[8] not in (None, 0)]
summ = dict(epic=EPIC, rows=len(rows), first=ts[0] if ts else None, last=ts[-1] if ts else None, requests=n_req, keys=keys_seen,
            vol_nonzero=len(vol), first_err=first_err, made_utc=end.isoformat())
json.dump(summ, open(f'data/{TAG}_hist_summary.json', 'w'), indent=1); print(json.dumps(summ, indent=1))
