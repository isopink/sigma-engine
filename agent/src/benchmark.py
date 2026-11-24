"""비교 기준 KODEX 200 (069500) 일봉 → docs/data/kodex200.json.
11-11 S.Lee: 대시보드의 비교선·초과수익을 KOSPI 지수 대신 KODEX 200 으로. 대회 시작일 시가가 기준(대회 게시판과 같은 09:00 가격).
마감 기록(close) 때 갱신하고, 실패해도 마감 기록은 계속함. 네이버 증권 일봉(공개, 키 없음)."""
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

CODE, NAME = "069500", "KODEX 200"
URL = f"https://fchart.stock.naver.com/sise.nhn?symbol={CODE}&timeframe=day&count=40&requestType=0"


def parse(xml):
    """네이버 일봉 응답 → {YYYY-MM-DD: {o, c}} (시가 · 종가)."""
    days = {}
    for line in re.findall(r'data="([^"]+)"', xml):
        d, o, _h, _l, c, _v = line.split("|")
        days[f"{d[:4]}-{d[4:6]}-{d[6:]}"] = {"o": float(o), "c": float(c)}
    return days


def build(days, start_date):
    days = {d: v for d, v in days.items() if d >= start_date}
    if start_date not in days:
        raise ValueError(f"{start_date} 일봉이 없음")
    return {"symbol": CODE, "name": NAME, "start_date": start_date, "start": days[start_date]["o"],
            "days": dict(sorted(days.items())), "updated": C.stamp()}


def update():
    xml = urllib.request.urlopen(URL, timeout=20).read().decode("euc-kr", errors="replace")
    out = build(parse(xml), C.params()["competition"]["start"])
    C.write_json(os.path.join(C.DOCS_DATA, "kodex200.json"), out)
    return out


# ---- 11-17 S.Lee: 대시보드에 S&P 500 도 겹쳐 그림 (참고선) ----
# 미국 장은 한국 장이 끝난 뒤 열리므로, 한국 날짜 d 에는 d 전날까지의 미국 종가를 씀.
# 기준 = 대회 시작일(한국 11-02) 아침에 알 수 있던 마지막 미국 종가 (10-30 금).
SPX_FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500&cosd={start}"
SPX_YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?range=3mo&interval=1d"


def spx_parse_fred(text):
    days = {}
    for line in text.strip().splitlines()[1:]:
        d, _, v = line.partition(",")
        try:
            days[d.strip()] = float(v)
        except ValueError:   # 휴장일은 '.'
            pass
    return days


def spx_parse_yahoo(js):
    import datetime as dt
    import json
    r = json.loads(js)["chart"]["result"][0]
    ny = dt.timezone(dt.timedelta(hours=-5))
    return {dt.datetime.fromtimestamp(t, ny).date().isoformat(): float(c)
            for t, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]) if c is not None}


def spx_build(days, start_date):
    before = [d for d in days if d < start_date]
    if not before:
        raise ValueError(f"{start_date} 전 S&P 500 종가가 없음")
    b = max(before)
    return {"symbol": "SPX", "name": "S&P 500", "base_date": b, "base": days[b],
            "days": {d: v for d, v in sorted(days.items()) if d >= b}, "updated": C.stamp()}


def update_spx():
    start = C.params()["competition"]["start"]
    import datetime as dt
    cosd = (dt.date.fromisoformat(start) - dt.timedelta(days=10)).isoformat()
    ua = {"User-Agent": "Mozilla/5.0"}
    try:   # 11-25 Yahoo 먼저 (FRED 는 하루 늦게 올라옴 → 실시간 선물 끝점과 기준 종가가 어긋남)
        days = spx_parse_yahoo(urllib.request.urlopen(urllib.request.Request(SPX_YAHOO, headers=ua), timeout=20).read().decode())
    except Exception:  # noqa: BLE001  Yahoo 가 안 되면 FRED
        txt = urllib.request.urlopen(urllib.request.Request(SPX_FRED.format(start=cosd), headers=ua), timeout=20).read().decode()
        days = spx_parse_fred(txt)
    path = os.path.join(C.DOCS_DATA, "spx.json")
    old = (C.read_json(path, {}) or {}).get("days") or {}
    out = spx_build({**old, **days}, start)   # 받아 온 값이 없는 날은 예전 값 유지
    C.write_json(path, out)
    return out


if __name__ == "__main__":
    rc = 0
    try:
        r = update()
        print(f"KODEX 200 기준 {len(r['days'])}일 · 시작 시가 {r['start']:,.0f} · 마지막 {max(r['days'])} 종가 {r['days'][max(r['days'])]['c']:,.0f}")
    except Exception as e:  # noqa: BLE001
        print(f"  ! KODEX 200 기준 갱신 실패: {e}")
        rc = 1
    try:
        s = update_spx()
        print(f"S&P 500 참고선 기준 {s['base_date']} {s['base']:,.2f} · 마지막 {max(s['days'])} {s['days'][max(s['days'])]:,.2f}")
    except Exception as e:  # noqa: BLE001
        print(f"  ! S&P 500 갱신 실패: {e}")
    sys.exit(rc)
