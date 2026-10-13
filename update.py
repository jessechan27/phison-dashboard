"""Get verified Phison (8299) data from official sources:

- TPEX afterTrading/dailyQuotes  收盤價、成交量
- TPEX insti/dailyTrade          三大法人買賣超
- TPEX margin/balance            融資融券餘額
- TPEX margin/sbl                借券賣出餘額
- TDCC smWeb/qryStock            集保戶股權分散表（每週，大戶持股）

Never invent data; preserve previous verified snapshot if upstream fails.
Every table is checked for the expected columns, the requested date and
internal totals before it is stored.
"""
import datetime
import http.cookiejar
import json
import os
import pathlib
import re
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent
OUTPUT = ROOT / 'data' / 'market.json'
TZ = ZoneInfo('Asia/Taipei')
CODE = '8299'
TPEX = 'https://www.tpex.org.tw/www/zh-tw/'
TDCC = 'https://www.tdcc.com.tw/portal/zh/smWeb/qryStock'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36'

def number(v):
    try:
        return float(str(v).strip().replace(',', '').replace('+', ''))
    except (ValueError, TypeError):
        return None

def lots(shares):
    return round(shares / 1000, 2)

def get(url, data=None, opener=None, tries=3):
    # TPEX tables are ~1 MB and occasionally drop mid-transfer (IncompleteRead),
    # so retry with a short backoff before giving up on the day.
    opener = opener or urllib.request.build_opener()
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={
                'User-Agent': UA, 'Accept': 'application/json,text/html', 'Referer': url})
            with opener.open(req, timeout=30) as response:
                return response.read()
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(3 * (attempt + 1))

def tpex(path, day, **params):
    params.update(response='json', date=day.strftime('%Y/%m/%d'))
    payload = json.loads(get(TPEX + path + '?' + urllib.parse.urlencode(params)))
    if str(payload.get('date')) != day.strftime('%Y%m%d'):
        raise ValueError(f'{path} answered for {payload.get("date")}, not {day}')
    return payload

def find_row(payload):
    """Return (fields, row) for 8299, or (None, None) when the day has no data."""
    for table in payload.get('tables', []):
        if not isinstance(table, dict):
            continue
        fields = [str(z).replace('\n', '').replace(' ', '') for z in table.get('fields') or []]
        for row in table.get('data') or []:
            if isinstance(row, list) and row and str(row[0]).strip() == CODE:
                return fields, row
    return None, None

def parse_quotes(payload):
    fields, row = find_row(payload)
    if row is None:
        return None
    col = lambda name: next((i for i, f in enumerate(fields) if name in f), None)
    close_i, vol_i = col('收盤'), col('成交股數')
    if close_i is None or vol_i is None:
        raise ValueError('dailyQuotes columns changed')
    close, shares = number(row[close_i]), number(row[vol_i])
    if close is None or shares is None or close <= 0 or shares < 0:
        return None
    return {'close': close, 'volume_lots': lots(shares)}

def parse_institutional(payload):
    fields, row = find_row(payload)
    if row is None:
        return None
    # TPEX repeats 買進/賣出/買賣超 headers, so the groups are positional:
    # 2-4 外資(不含外資自營商) 5-7 外資自營商 8-10 外資合計 11-13 投信
    # 14-16 自營商(自行買賣) 17-19 自營商(避險) 20-22 自營商合計 23 三大法人合計
    if len(fields) < 24 or len(row) < 24 or '合計' not in fields[23]:
        raise ValueError('三大法人 columns changed')
    v = [number(z) for z in row]
    foreign, trust, dealer, total = v[10], v[13], v[22], v[23]
    if None in (foreign, trust, dealer, total, v[4], v[7], v[16], v[19]):
        raise ValueError('三大法人 row has blanks')
    if v[4] + v[7] != foreign or v[16] + v[19] != dealer or foreign + trust + dealer != total:
        raise ValueError('三大法人 subtotals do not reconcile')
    return {'foreign_net': lots(foreign), 'trust_net': lots(trust),
            'dealer_net': lots(dealer), 'inst_net': lots(total)}

def parse_margin(payload):
    fields, row = find_row(payload)
    if row is None:
        return None
    col = {f: i for i, f in enumerate(fields)}
    need = ('前資餘額(張)', '資餘額', '資使用率(%)', '前券餘額(張)', '券餘額')
    if any(n not in col for n in need):
        raise ValueError('融資融券 columns changed')
    prev_m, margin, usage, prev_s, short = (number(row[col[n]]) for n in need)
    if None in (prev_m, margin, prev_s, short):
        raise ValueError('融資融券 row has blanks')
    return {'margin_balance': margin, 'margin_change': margin - prev_m,
            'margin_usage': usage, 'short_balance': short, 'short_change': short - prev_s}

def parse_sbl(payload):
    fields, row = find_row(payload)
    if row is None:
        return None
    # Columns 2-7 are 融券; 8-12 are 借券賣出 前日餘額/當日賣出/當日還券/當日調整數額/當日餘額 (股).
    if len(fields) < 13 or len(row) < 13 or fields[9] != '當日賣出' or fields[10] != '當日還券' \
            or fields[12] != '當日餘額':
        raise ValueError('借券賣出 columns changed')
    prev, sold, returned, adjust, balance = (number(z) for z in row[8:13])
    if None in (prev, sold, returned, adjust, balance):
        raise ValueError('借券賣出 row has blanks')
    if prev + sold - returned + adjust != balance:
        raise ValueError('借券賣出 balance does not reconcile')
    return {'sbl_balance': lots(balance), 'sbl_change': lots(balance - prev)}

# (name, path, extra params, parser, key that marks the day as done)
DAILY_SOURCES = [
    ('三大法人', 'insti/dailyTrade', {'type': 'Daily', 'sect': 'EW'}, parse_institutional, 'inst_net'),
    ('融資融券', 'margin/balance', {}, parse_margin, 'margin_balance'),
    ('借券賣出', 'margin/sbl', {}, parse_sbl, 'sbl_balance'),
]

def html_text(cell):
    return re.sub(r'<[^>]+>|\s+', '', cell)

def parse_holders(html, week):
    m = re.search(r'資料日期：\s*(\d+)年(\d+)月(\d+)日', html)
    if not m or datetime.date(int(m[1]) + 1911, int(m[2]), int(m[3])) != week:
        raise ValueError('TDCC answered for a different week')
    start = html.find('<table', html.find('占集保庫存數比例') - 3000)
    table = html[start:html.find('</table>', start)]
    rows = [[html_text(c) for c in re.findall(r'<td[^>]*>(.*?)</td>', r, re.S)]
            for r in re.findall(r'<tr[^>]*>(.*?)</tr>', table, re.S)]
    rows = [r for r in rows if len(r) == 5]
    levels = [r for r in rows if r[0].isdigit() and int(r[0]) <= 15]
    total = next((r for r in rows if r[1] == '合計'), None)
    if len(levels) != 15 or total is None or not levels[14][1].startswith('1,000,001') \
            or not levels[11][1].startswith('400,001'):
        raise ValueError('TDCC table layout changed')
    people = [number(r[2]) for r in levels]
    shares = [number(r[3]) for r in levels]
    pcts = [number(r[4]) for r in levels]  # TDCC's published ratios, so figures match its site
    if None in people + shares + pcts or not number(total[2]):
        raise ValueError('TDCC table has blanks')
    return {'date': week.isoformat(), 'holders': int(number(total[2])),
            'over400_pct': round(sum(pcts[11:]), 2), 'over400_holders': int(sum(people[11:])),
            'over1000_pct': pcts[14], 'over1000_holders': int(people[14]),
            'levels': [[r[1], int(p), lots(s), c] for r, p, s, c in zip(levels, people, shares, pcts)]}

def fetch_holders(known, weeks, errors):
    """集保戶股權分散表 for the newest `weeks` weeks not already stored."""
    found = []
    page = get(TDCC).decode('utf-8')
    options = re.findall(r'<option value="(\d{8})"', page)[:weeks]
    for value in options:
        week = datetime.datetime.strptime(value, '%Y%m%d').date()
        if week.isoformat() in known:
            continue
        try:
            # The form token is single-use and tied to the session cookie.
            opener = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            page = get(TDCC, opener=opener).decode('utf-8')
            field = lambda name: re.search(rf'name="{name}" value="([^"]*)"', page)[1]
            form = {'SYNCHRONIZER_TOKEN': field('SYNCHRONIZER_TOKEN'),
                    'SYNCHRONIZER_URI': '/portal/zh/smWeb/qryStock', 'method': 'submit',
                    'firDate': field('firDate'), 'scaDate': value, 'sqlMethod': 'StockNo',
                    'stockNo': CODE, 'stockName': ''}
            html = get(TDCC, urllib.parse.urlencode(form).encode(), opener, tries=1).decode('utf-8')
            found.append(parse_holders(html, week))
        except Exception as exc:
            errors.append(f'{week} 集保: {exc}')
    return found

def main():
    old = {'history': []}
    if OUTPUT.exists():
        try:
            old = json.loads(OUTPUT.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            pass
    history = {x['date']: x for x in old.get('history', []) if 'date' in x}
    holders = {x['date']: x for x in old.get('holders', []) if 'date' in x}
    today = datetime.datetime.now(TZ).date()
    errors = []
    # Backfill the preceding 120 calendar days on first run, then update the last 7.
    # BACKFILL_DAYS overrides this to re-fill older gaps or newly added fields.
    lookback = int(os.environ.get('BACKFILL_DAYS') or (120 if len(history) < 30 else 7))
    for ago in range(lookback, -1, -1):
        day = today - datetime.timedelta(days=ago)
        if day.weekday() >= 5:
            continue
        entry = dict(history.get(day.isoformat(), {'date': day.isoformat()}))
        try:
            if 'close' not in entry:
                quote = parse_quotes(tpex('afterTrading/dailyQuotes', day))
                if not quote:
                    continue  # market holiday, or today's close is not published yet
                entry.update(quote)
        except Exception as exc:
            errors.append(f'{day}: {exc}')
            continue
        # Margin and SBL tables are published later in the evening than quotes;
        # an empty table leaves the field missing so a later run fills it in.
        for name, path, params, parser, done in DAILY_SOURCES:
            if done in entry:
                continue
            try:
                result = parser(tpex(path, day, **params))
                if result:
                    entry.update(result)
            except Exception as exc:
                errors.append(f'{day} {name}: {exc}')
        history[day.isoformat()] = entry
    try:
        for week in fetch_holders(set(holders), 26 if len(holders) < 4 else 4, errors):
            holders[week['date']] = week
    except Exception as exc:
        errors.append(f'集保: {exc}')
    if not history:
        raise RuntimeError('TPEX did not return any verifiable 8299 rows. ' + '; '.join(errors[-3:]))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({
        'symbol': '8299', 'source': 'TPEX dailyQuotes / 三大法人 / 融資融券 / 借券賣出; TDCC 集保戶股權分散表',
        'fetched_at': datetime.datetime.now(TZ).isoformat(timespec='seconds'),
        'history': [history[k] for k in sorted(history)][-250:],
        'holders': [holders[k] for k in sorted(holders)][-60:],
        'warnings': errors[-10:]
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Latest verified trading day:', max(history), 'records:', len(history),
          'holder weeks:', len(holders), 'warnings:', len(errors))
    for line in errors[-10:]:
        print('  warning:', line)

if __name__ == '__main__':
    main()
