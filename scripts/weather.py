# -*- coding: utf-8 -*-
"""
天気予報パーツ（build.py から呼び出し）
- 全国主要17都市の週間天気予報（東日本／西日本）
- 全国の天気マップ（今日／17時以降は明日）
- 千代田区の1時間ごとの天気予報
地図：国土地理院「地球地図日本」をもとに作成（jpn-atlas, BSD-3-Clause）
データ：Open-Meteo（無料・登録不要。日本付近は気象庁モデル等を使用） https://open-meteo.com/
"""
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
UA = "Mozilla/5.0 market-board-signage"

EAST = [("札幌", 43.0621, 141.3544), ("釧路", 42.9849, 144.3820), ("秋田", 39.7200, 140.1025),
        ("仙台", 38.2682, 140.8694), ("新潟", 37.9161, 139.0364), ("長野", 36.6485, 138.1950),
        ("東京", 35.6940, 139.7536), ("小笠原", 27.0944, 142.1914)]
WEST = [("金沢", 36.5613, 136.6562), ("名古屋", 35.1815, 136.9066), ("大阪", 34.6937, 135.5023),
        ("松江", 35.4723, 133.0505), ("広島", 34.3853, 132.4553), ("高知", 33.5597, 133.5311),
        ("福岡", 33.5904, 130.4017), ("鹿児島", 31.5966, 130.5571), ("那覇", 26.2124, 127.6809)]

# 天気マップ上の位置： 都市名 → (地図上の点 x,y, カード左上 x,y)  ※1920x1080の画面座標
MAP_POS = {
    "札幌": (1152, 351, 975, 220), "釧路": (1275, 349, 1450, 352), "秋田": (1105, 537, 1225, 392),
    "仙台": (1139, 616, 1225, 542), "新潟": (1060, 637, 900, 448), "長野": (1023, 707, 1225, 842),
    "東京": (1093, 760, 1225, 692), "小笠原": (1679, 912, 1740, 862), "金沢": (954, 711, 742, 455),
    "名古屋": (964, 788, 1058, 888), "大阪": (900, 814, 902, 888), "松江": (790, 766, 714, 606),
    "広島": (760, 824, 556, 596), "高知": (807, 873, 746, 888), "福岡": (663, 862, 430, 748),
    "鹿児島": (662, 972, 430, 888), "那覇": (395, 300, 600, 186),
}
CARD_W, CARD_H = 150, 140
CHIYODA = (35.6940, 139.7536)

API = "https://api.open-meteo.com/v1/forecast"


def _get_json(params):
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_weather():
    """成功した部分だけ返す（失敗時は None を入れる → 前回値を使う）"""
    out = {}
    cities = EAST + WEST
    try:
        res = _get_json({
            "latitude": ",".join(str(c[1]) for c in cities),
            "longitude": ",".join(str(c[2]) for c in cities),
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "timezone": "Asia/Tokyo", "forecast_days": 7,
        })
        if isinstance(res, dict):
            res = [res]
        weekly = {}
        if len(res) != len(cities):
            raise ValueError("city count mismatch")
        for (name, _, _), r in zip(cities, res):
            d = r["daily"]
            weekly[name] = [{"date": d["time"][i], "code": d["weather_code"][i],
                             "tmax": d["temperature_2m_max"][i], "tmin": d["temperature_2m_min"][i],
                             "pop": d["precipitation_probability_max"][i]} for i in range(len(d["time"]))]
        out["weekly"] = weekly
    except Exception as e:
        print("weather weekly NG", e, file=sys.stderr)
    try:
        r = _get_json({
            "latitude": CHIYODA[0], "longitude": CHIYODA[1],
            "hourly": "weather_code,temperature_2m,precipitation,precipitation_probability,"
                      "wind_speed_10m,wind_direction_10m,is_day",
            "wind_speed_unit": "ms", "timezone": "Asia/Tokyo", "forecast_days": 3,
        })
        h = r["hourly"]
        out["hourly"] = [{"time": h["time"][i], "code": h["weather_code"][i], "temp": h["temperature_2m"][i],
                          "prec": h["precipitation"][i], "pop": h["precipitation_probability"][i],
                          "ws": h["wind_speed_10m"][i], "wd": h["wind_direction_10m"][i],
                          "day": h["is_day"][i]} for i in range(len(h["time"]))]
    except Exception as e:
        print("weather hourly NG", e, file=sys.stderr)
    return out


# ---------------- アイコン（インラインSVG・古いブラウザ対応） ----------------
SUN = ('<circle cx="32" cy="32" r="12" fill="#ffb300"/>'
       '<g stroke="#ffb300" stroke-width="4" stroke-linecap="round">'
       '<line x1="32" y1="6" x2="32" y2="13"/><line x1="32" y1="51" x2="32" y2="58"/>'
       '<line x1="6" y1="32" x2="13" y2="32"/><line x1="51" y1="32" x2="58" y2="32"/>'
       '<line x1="13.6" y1="13.6" x2="18.5" y2="18.5"/><line x1="45.5" y1="45.5" x2="50.4" y2="50.4"/>'
       '<line x1="13.6" y1="50.4" x2="18.5" y2="45.5"/><line x1="45.5" y1="18.5" x2="50.4" y2="13.6"/></g>')
MOON = '<path d="M40 10a22 22 0 1 0 14 34A18 18 0 0 1 40 10z" fill="#f2c94c"/>'
CLOUD = ('<path d="M18 50h30a11 11 0 0 0 0-22 15 15 0 0 0-28-3 10 10 0 0 0-2 25z" '
         'fill="#b8c4d2" stroke="#8795a8" stroke-width="2"/>')
CLOUD_DARK = ('<path d="M18 44h30a11 11 0 0 0 0-22 15 15 0 0 0-28-3 10 10 0 0 0-2 25z" '
              'fill="#8e9bad" stroke="#6b788b" stroke-width="2"/>')
SMALL_SUN = ('<circle cx="22" cy="22" r="10" fill="#ffb300"/>'
             '<g stroke="#ffb300" stroke-width="3.5" stroke-linecap="round">'
             '<line x1="22" y1="3" x2="22" y2="8"/><line x1="3" y1="22" x2="8" y2="22"/>'
             '<line x1="8.6" y1="8.6" x2="12" y2="12"/><line x1="35.4" y1="8.6" x2="32" y2="12"/></g>')
SMALL_MOON = '<path d="M26 6a15 15 0 1 0 10 24A12 12 0 0 1 26 6z" fill="#f2c94c"/>'
RAIN = ('<g stroke="#1f6fe0" stroke-width="4" stroke-linecap="round">'
        '<line x1="22" y1="50" x2="18" y2="60"/><line x1="33" y1="50" x2="29" y2="60"/>'
        '<line x1="44" y1="50" x2="40" y2="60"/></g>')
DRIZZLE = ('<g stroke="#1f6fe0" stroke-width="4" stroke-linecap="round">'
           '<line x1="25" y1="51" x2="23" y2="57"/><line x1="40" y1="51" x2="38" y2="57"/></g>')
SNOW = ('<g fill="#6fa8ff"><circle cx="20" cy="55" r="4"/><circle cx="32" cy="58" r="4"/>'
        '<circle cx="44" cy="55" r="4"/></g>')
BOLT = '<path d="M34 44l-8 12h7l-4 8 11-13h-7l4-7z" fill="#ffc107" stroke="#e0a000" stroke-width="1"/>'
FOG = ('<g stroke="#8795a8" stroke-width="4" stroke-linecap="round">'
       '<line x1="10" y1="52" x2="54" y2="52"/><line x1="16" y1="60" x2="48" y2="60"/></g>')


def classify(code):
    """WMO天気コード → (種類, 日本語ラベル)"""
    c = int(code) if code is not None else -1
    if c == 0: return "sun", "快晴"
    if c == 1: return "sun", "晴れ"
    if c == 2: return "partly", "晴れ時々曇り"
    if c == 3: return "cloud", "曇り"
    if c in (45, 48): return "fog", "霧"
    if 51 <= c <= 57: return "drizzle", "小雨"
    if 61 <= c <= 67 or 80 <= c <= 82: return "rain", "雨"
    if 71 <= c <= 77 or c in (85, 86): return "snow", "雪"
    if c >= 95: return "thunder", "雷雨"
    return "cloud", "―"


def icon(code, size, day=True):
    kind, _ = classify(code)
    if kind == "sun":
        body = SUN if day else MOON
    elif kind == "partly":
        body = (SMALL_SUN if day else SMALL_MOON) + CLOUD
    elif kind == "cloud":
        body = CLOUD
    elif kind == "fog":
        body = CLOUD_DARK.replace("M18 44", "M18 40") + FOG
    elif kind == "drizzle":
        body = CLOUD_DARK + DRIZZLE
    elif kind == "rain":
        body = CLOUD_DARK + RAIN
    elif kind == "snow":
        body = CLOUD_DARK + SNOW
    else:
        body = CLOUD_DARK + BOLT
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 64 64">%s</svg>'
            % (size, size, body))


WEEK = "月火水木金土日"
DIR16 = ["北", "北北東", "北東", "東北東", "東", "東南東", "南東", "南南東",
         "南", "南南西", "南西", "西南西", "西", "西北西", "北西", "北北西"]


def _r(v):
    return "―" if v is None else "%d" % round(v)


def render_weekly(weekly, cities, title):
    if not weekly:
        return '<div class="wx-empty">天気データを取得できませんでした</div>'
    first = next((weekly[c[0]] for c in cities if c[0] in weekly), None)
    if not first:
        return '<div class="wx-empty">天気データを取得できませんでした</div>'
    head = ['<th class="wc">%s</th>' % title]
    for d in first:
        dt = datetime.strptime(d["date"], "%Y-%m-%d")
        wd = dt.weekday()
        cls = " sat" if wd == 5 else (" sun" if wd == 6 else "")
        head.append('<th class="wd%s">%d/%d<span>（%s）</span></th>' % (cls, dt.month, dt.day, WEEK[wd]))
    rows = []
    for name, _, _ in cities:
        days = weekly.get(name)
        if not days:
            continue
        cells = ['<td class="wn">%s</td>' % name]
        for d in days:
            wd = datetime.strptime(d["date"], "%Y-%m-%d").weekday()
            cls = " sat" if wd == 5 else (" sun" if wd == 6 else "")
            pop = "" if d["pop"] is None else "%d%%" % d["pop"]
            cells.append(
                '<td class="wv%s"><table class="wi"><tr><td class="ic">%s</td>'
                '<td class="tt"><span class="hi">%s</span><span class="sl">/</span><span class="lo">%s</span>'
                '<div class="pp">&#9730; %s</div></td></tr></table></td>'
                % (cls, icon(d["code"], 58), _r(d["tmax"]), _r(d["tmin"]), pop))
        rows.append("<tr>%s</tr>" % "".join(cells))
    return '<table class="wk"><tr>%s</tr>%s</table>' % ("".join(head), "".join(rows))


def render_hourly(hourly):
    """24時間分を出力し、表示時にJSで『現在時刻以降の12時間』だけを見せる"""
    if not hourly:
        return '<div class="wx-empty">天気データを取得できませんでした</div>'
    now = datetime.now(JST).replace(minute=0, second=0, microsecond=0)
    items = []
    prev_day = None
    for h in hourly:
        t = datetime.strptime(h["time"], "%Y-%m-%dT%H:%M").replace(tzinfo=JST)
        if t < now - timedelta(hours=1) or t > now + timedelta(hours=30):
            continue
        _, label = classify(h["code"])
        dir_ = "" if h["wd"] is None else DIR16[int((h["wd"] + 11.25) % 360 // 22.5)]
        day_label = "%d/%d（%s）" % (t.month, t.day, WEEK[t.weekday()])
        items.append(
            '<div class="hc" data-t="%d"><div class="hd">%s</div><div class="ht">%d:00</div>'
            '<div class="hi2">%s</div><div class="hl">%s</div>'
            '<div class="hT">%s<span>℃</span></div>'
            '<div class="hr">&#9730; %s<span>mm</span>　%s</div>'
            '<div class="hw">%s %s<span>m/s</span></div></div>'
            % (int(t.timestamp()), day_label, t.hour, icon(h["code"], 104, bool(h["day"])), label,
               "―" if h["temp"] is None else "%.0f" % h["temp"],
               "―" if h["prec"] is None else "%.1f" % h["prec"],
               "" if h["pop"] is None else "%d%%" % h["pop"],
               dir_, "―" if h["ws"] is None else "%.0f" % h["ws"]))
    return '<div id="hgrid">%s</div>' % "".join(items)


def render_map(weekly):
    """全国天気マップ（今日。17時以降は明日）"""
    if not weekly:
        return '<div class="wx-empty">天気データを取得できませんでした</div>', ""
    now = datetime.now(JST)
    idx = 1 if now.hour >= 17 else 0
    lines, cards, label = [], [], ""
    for name, (px, py, cx, cy) in MAP_POS.items():
        days = weekly.get(name)
        if not days or len(days) <= idx:
            continue
        d = days[idx]
        if not label:
            dt = datetime.strptime(d["date"], "%Y-%m-%d")
            label = "%s（%d/%d %s）" % ("明日" if idx else "今日", dt.month, dt.day, WEEK[dt.weekday()])
        ccx, ccy = cx + CARD_W // 2, cy + CARD_H // 2
        lines.append('<line x1="%d" y1="%d" x2="%d" y2="%d"/>' % (px, py, ccx, ccy))
        lines.append('<circle cx="%d" cy="%d" r="6"/>' % (px, py))
        pop = "" if d["pop"] is None else "%d%%" % d["pop"]
        cards.append(
            '<div class="mc" style="left:%dpx;top:%dpx;"><div class="mn">%s</div>%s'
            '<div class="mt"><span class="hi">%s</span><span class="sl">/</span><span class="lo">%s</span></div>'
            '<div class="mp">&#9730; %s</div></div>'
            % (cx, cy, name, icon(d["code"], 50), _r(d["tmax"]), _r(d["tmin"]), pop))
    import os
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "japan_map.svg"), encoding="utf-8") as f:
            base = f.read()
    except Exception:
        base = '<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080"></svg>'
    overlay = '<g stroke="#e0357f" stroke-width="2" fill="#e0357f">%s</g></svg>' % "".join(lines)
    svg = base.replace("</svg>", overlay)
    svg = svg.replace("<svg ", '<svg class="jmap" ', 1)
    return svg + "".join(cards), label
