"""Get verified Phison (8299) end-of-day quotes from the TPEX dailyQuotes endpoint.
Never invent data; preserve previous verified snapshot if upstream fails.
"""
import datetime
import json
import pathlib
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent
OUTPUT = ROOT / 'data' / 'market.json'
TZ = ZoneInfo('Asia/Taipei')

def number(v):
    try:
        return float(str(v).strip().replace(',', '').replace('+', ''))
    except (ValueError, TypeError):
        return None

def fetch(day):
    url = 'https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?' + urllib.parse.urlencode({
        'response': 'json', 'date': day.strftime('%Y/%m/%d')})
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)

def tables(payload):
    if isinstance(payload, dict):
        for table in payload.get('tables', []):
            if isinstance(table, dict):
                yield table.get('fields', []), table.get('data', [])
        if isinstance(payload.get('data'), list):
            yield payload.get('fields', []), payload['data']
    elif isinstance(payload, list):
        yield [], payload

def parse(payload, date):
    for fields, rows in tables(payload):
        fields = [str(z).replace('\n', '').replace(' ', '') for z in fields]
        for row in rows:
            if not isinstance(row, list) or '8299' not in [str(z).strip() for z in row[:3]]:
                continue
            # Standard TPEX dailyQuotes columns: 代號, 名稱, 收盤, 漲跌, 開盤,
            # 最高, 最低, 均價, 成交股數, 成交金額, 成交筆數, ...
            if fields:
                def col(name):
                    return next((i for i, f in enumerate(fields) if name in f), None)
                code_i = col('代號')
                close_i = col('收盤')
                vol_i = col('成交股數')
                if code_i is None or close_i is None or vol_i is None:
                    continue
            else:
                # Without column metadata, do not assume undocumented order.
                continue
            if str(row[code_i]).strip() != '8299':
                continue
            close = number(row[close_i]); shares = number(row[vol_i])
            if close is None or shares is None or close <= 0 or shares < 0:
                continue
            return {'date': date.isoformat(), 'close': close,
                    'volume_lots': round(shares / 1000, 2)}
    return None

def main():
    old = {'history': []}
    if OUTPUT.exists():
        try:
            old = json.loads(OUTPUT.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            pass
    history = {x['date']: x for x in old.get('history', []) if 'date' in x}
    today = datetime.datetime.now(TZ).date()
    errors = []
    # Backfill the preceding 120 calendar days on first run, then update the last 7.
    lookback = 120 if len(history) < 30 else 7
    for ago in range(lookback, -1, -1):
        day = today - datetime.timedelta(days=ago)
        if day.weekday() >= 5 or day.isoformat() in history:
            continue
        try:
            entry = parse(fetch(day), day)
            if entry:
                history[entry['date']] = entry
        except Exception as exc:
            errors.append(f'{day}: {exc}')
    if not history:
        raise RuntimeError('TPEX did not return any verifiable 8299 rows. ' + '; '.join(errors[-3:]))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({
        'symbol': '8299', 'source': 'TPEX dailyQuotes',
        'fetched_at': datetime.datetime.now(TZ).isoformat(timespec='seconds'),
        'history': [history[k] for k in sorted(history)][-250:],
        'warnings': errors[-10:]
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Latest verified trading day:', max(history), 'records:', len(history))

if __name__ == '__main__':
    main()
