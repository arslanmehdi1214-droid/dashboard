"""Client-sentiment recorder (23 Oct 2026, his yes): once a minute, reads Capital.com's client sentiment (% of Capital.com clients
long vs short) for the desk markets and appends one row per market to data/sentiment/YYYY-MM-DD.csv (UTC date).
READ-ONLY research data: no orders, no account data. Uses the same CAPITAL_* demo key as the desk. Never raises into the loop.
Status of the last call (ok / error text) goes to data/sentiment/status.json so the recording can be checked."""
import os, json, time, datetime as dt, requests

BASE = 'https://demo-api-capital.backend-capital.com' if os.environ.get('CAPITAL_DEMO', '1') == '1' else 'https://api-capital.backend-capital.com'
MARKETS = ['USDJPY', 'GOLD', 'OIL_CRUDE', 'US100', 'US500', 'SILVER']
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'sentiment')
_S = {'h': None, 'last': None}

def _login():
    r = requests.post(BASE + '/api/v1/session', timeout=15, headers={'X-CAP-API-KEY': os.environ['CAPITAL_API_KEY'], 'Content-Type': 'application/json'},
                      json={'identifier': os.environ['CAPITAL_IDENTIFIER'], 'password': os.environ['CAPITAL_API_PASSWORD'], 'encryptedPassword': False})
    r.raise_for_status(); _S['h'] = {'X-SECURITY-TOKEN': r.headers['X-SECURITY-TOKEN'], 'CST': r.headers['CST']}

def _get(path, params=None):
    if _S['h'] is None: _login()
    r = requests.get(BASE + path, headers=_S['h'], params=params, timeout=10)
    if r.status_code in (401, 403):                                    # session expired -> one fresh login
        _login(); r = requests.get(BASE + path, headers=_S['h'], params=params, timeout=10)
    return r

def _status(obj):
    try:
        os.makedirs(OUT, exist_ok=True); json.dump(obj, open(os.path.join(OUT, 'status.json'), 'w'), indent=1)
    except Exception: pass

def record():
    """Call once a minute. Returns a short text for the log."""
    now = dt.datetime.now(dt.timezone.utc).replace(second=0, microsecond=0)
    if _S['last'] == now: return 'sentiment: already this minute'
    _S['last'] = now
    try:
        r = _get('/api/v1/clientsentiment', {'marketIds': ','.join(MARKETS)})
        rows = []
        if r.status_code == 200:
            items = r.json().get('clientSentiments') or []
            for it in items:
                rows.append((it.get('marketId'), it.get('longPositionPercentage'), it.get('shortPositionPercentage')))
        if not rows:                                                   # fallback: one market at a time
            first_err = f'{r.status_code} {r.text[:200]}'
            for m in MARKETS:
                q = _get(f'/api/v1/clientsentiment/{m}')
                if q.status_code == 200:
                    it = q.json(); it = it.get('clientSentiment', it)
                    rows.append((it.get('marketId', m), it.get('longPositionPercentage'), it.get('shortPositionPercentage')))
                time.sleep(0.12)
            if not rows:
                _status({'t': now.isoformat(), 'ok': False, 'error': first_err}); return 'sentiment: no data (' + first_err[:80] + ')'
        os.makedirs(OUT, exist_ok=True); f = os.path.join(OUT, now.strftime('%Y-%m-%d') + '.csv'); new = not os.path.exists(f)
        with open(f, 'a') as fh:
            if new: fh.write('utc,market,long_pct,short_pct\n')
            for m, lo, sh in rows: fh.write(f'{now:%Y-%m-%d %H:%M},{m},{lo},{sh}\n')
        _status({'t': now.isoformat(), 'ok': True, 'markets': len(rows), 'sample': rows[:2]})
        return f'sentiment: {len(rows)} markets'
    except Exception as e:
        _S['h'] = None; _status({'t': now.isoformat(), 'ok': False, 'error': f'{type(e).__name__}: {str(e)[:200]}'})
        return 'sentiment error: ' + type(e).__name__
