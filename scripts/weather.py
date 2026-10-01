# -*- coding: utf-8 -*-
"""
天気予報パーツ（build.py から呼び出し）
- 全国主要17都市の週間天気予報（東日本／西日本）
- 全国の天気マップ（今日）
- 千代田区の1時間ごとの天気予報
地図：国土地理院「地球地図日本」をもとに作成（jpn-atlas, BSD-3-Clause）
データ：週間天気・全国マップ … 気象庁の天気予報（府県天気予報・週間天気予報）
      1時間天気 … Open-Meteo（気象庁の数値予報モデル） https://open-meteo.com/
      ※気象庁データが取れない都市だけ Open-Meteo の値で代用
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
    "東京": (1093, 760, 1225, 692), "小笠原": (1679, 912, 1740, 862), "金沢": (954, 711, 742, 448),
    "名古屋": (964, 788, 1058, 888), "大阪": (900, 814, 902, 888), "松江": (790, 766, 714, 604),
    "広島": (760, 824, 556, 586), "高知": (807, 873, 746, 888), "福岡": (663, 862, 430, 737),
    "鹿児島": (662, 972, 430, 888), "那覇": (395, 300, 600, 186),
}
CARD_W, CARD_H = 150, 146

# 気象庁 予報区（office）と、使う地域名・観測地点名
#   都市名: (officeコード, 短期予報の地域名, 週間予報の地域名, 気温の地点名)  ※地域名は前方一致、None は先頭
JMA = {
    "札幌": ("016000", "石狩", "石狩", "札幌"), "釧路": ("014100", "釧路", None, "釧路"),
    "秋田": ("050000", "沿岸", None, "秋田"), "仙台": ("040000", "東部", None, "仙台"),
    "新潟": ("150000", "下越", None, "新潟"), "長野": ("200000", "北部", None, "長野"),
    "東京": ("130000", "東京", "東京", "東京"), "小笠原": ("130000", "小笠原", "小笠原", "父島"),
    "金沢": ("170000", "加賀", None, "金沢"), "名古屋": ("230000", "西部", None, "名古屋"),
    "大阪": ("270000", None, None, "大阪"), "松江": ("320000", "東部", None, "松江"),
    "広島": ("340000", "南部", None, "広島"), "高知": ("390000", "中部", None, "高知"),
    "福岡": ("400000", "福岡", None, "福岡"), "鹿児島": ("460100", "薩摩", None, "鹿児島"),
    "那覇": ("471000", "本島中南部", None, "那覇"),
}
JMA_URL = "https://www.jma.go.jp/bosai/forecast/data/forecast/%s.json"

# 気象庁の天気コード → 表示名（主なもの）
TELOP = {
 100:"晴れ",101:"晴れ時々曇り",102:"晴れ一時雨",103:"晴れ時々雨",104:"晴れ一時雪",105:"晴れ時々雪",
 106:"晴れ一時雨か雪",107:"晴れ時々雨か雪",108:"晴れ一時雨か雷雨",110:"晴れのち時々曇り",111:"晴れのち曇り",
 112:"晴れのち一時雨",113:"晴れのち時々雨",114:"晴れのち雨",115:"晴れのち一時雪",116:"晴れのち時々雪",
 117:"晴れのち雪",118:"晴れのち雨か雪",119:"晴れのち雨か雷雨",120:"晴れ朝夕一時雨",121:"晴れ朝の内一時雨",
 122:"晴れ夕方一時雨",123:"晴れ山沿い雷雨",124:"晴れ山沿い雪",125:"晴れ午後は雷雨",126:"晴れ昼頃から雨",
 127:"晴れ夕方から雨",128:"晴れ夜は雨",130:"朝の内霧のち晴れ",131:"晴れ明け方霧",132:"晴れ朝夕曇り",
 140:"晴れ時々雨で雷を伴う",160:"晴れ一時雪か雨",170:"晴れ時々雪か雨",181:"晴れのち雪か雨",
 200:"曇り",201:"曇り時々晴れ",202:"曇り一時雨",203:"曇り時々雨",204:"曇り一時雪",205:"曇り時々雪",
 206:"曇り一時雨か雪",207:"曇り時々雨か雪",208:"曇り一時雨か雷雨",209:"霧",210:"曇りのち時々晴れ",
 211:"曇りのち晴れ",212:"曇りのち一時雨",213:"曇りのち時々雨",214:"曇りのち雨",215:"曇りのち一時雪",
 216:"曇りのち時々雪",217:"曇りのち雪",218:"曇りのち雨か雪",219:"曇りのち雨か雷雨",220:"曇り朝夕一時雨",
 221:"曇り朝の内一時雨",222:"曇り夕方一時雨",223:"曇り日中時々晴れ",224:"曇り昼頃から雨",225:"曇り夕方から雨",
 226:"曇り夜は雨",228:"曇り昼頃から雪",229:"曇り夕方から雪",230:"曇り夜は雪",231:"曇り海上海岸は霧か霧雨",
 240:"曇り時々雨で雷を伴う",250:"曇り時々雪で雷を伴う",260:"曇り一時雪か雨",270:"曇り時々雪か雨",281:"曇りのち雪か雨",
 300:"雨",301:"雨時々晴れ",302:"雨時々止む",303:"雨時々雪",304:"雨か雪",306:"大雨",308:"雨で暴風を伴う",
 309:"雨一時雪",311:"雨のち晴れ",313:"雨のち曇り",314:"雨のち時々雪",315:"雨のち雪",316:"雨か雪のち晴れ",
 317:"雨か雪のち曇り",320:"朝の内雨のち晴れ",321:"朝の内雨のち曇り",322:"雨朝晩一時雪",323:"雨昼頃から晴れ",
 324:"雨夕方から晴れ",325:"雨夜は晴れ",326:"雨夕方から雪",327:"雨夜は雪",328:"雨一時強く降る",329:"雨一時みぞれ",
 340:"雪か雨",350:"雨で雷を伴う",361:"雪か雨のち晴れ",371:"雪か雨のち曇り",
 400:"雪",401:"雪時々晴れ",402:"雪時々止む",403:"雪時々雨",405:"大雪",406:"風雪強い",407:"暴風雪",409:"雪一時雨",
 411:"雪のち晴れ",413:"雪のち曇り",414:"雪のち雨",420:"朝の内雪のち晴れ",421:"朝の内雪のち曇り",422:"雪昼頃から雨",
 423:"雪夕方から雨",425:"雪一時強く降る",426:"雪のちみぞれ",427:"雪一時みぞれ",450:"雪で雷を伴う",
}
CHIYODA = (35.6940, 139.7536)

API = "https://api.open-meteo.com/v1/forecast"


def _get_json(params):
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _pick(areas, prefix, key="area"):
    if not areas:
        return None
    if prefix:
        for a in areas:
            if a[key]["name"].startswith(prefix):
                return a
    return areas[0]


def _num(v):
    try:
        return float(v) if v not in ("", None, "--") else None
    except Exception:
        return None


def fetch_jma():
    """気象庁の府県天気予報・週間天気予報から 都市名 → 7日分 を作る"""
    today = datetime.now(JST).date()
    days = [(today + timedelta(days=i)).isoformat() for i in range(7)]
    cache, out = {}, {}
    for name, (office, sarea, warea, station) in JMA.items():
        try:
            if office not in cache:
                cache[office] = _http_json(JMA_URL % office)
            short, week = cache[office][0], cache[office][1]
            rec = {d: {"date": d, "code": None, "tmax": None, "tmin": None, "pop": None, "jma": True} for d in days}
            # --- 週間予報（明日以降の基本） ---
            ts0 = week["timeSeries"][0]
            a = _pick(ts0["areas"], warea or sarea)
            for i, t in enumerate(ts0["timeDefines"]):
                d = t[:10]
                if d in rec:
                    rec[d]["code"] = int(a["weatherCodes"][i])
                    rec[d]["pop"] = _num(a.get("pops", [""] * 7)[i])
            ts1 = week["timeSeries"][1]
            st = _pick(ts1["areas"], station)
            for i, t in enumerate(ts1["timeDefines"]):
                d = t[:10]
                if d in rec:
                    rec[d]["tmin"] = _num(st["tempsMin"][i])
                    rec[d]["tmax"] = _num(st["tempsMax"][i])
            # --- 府県天気予報（今日・明日はこちらを優先） ---
            sts = short["timeSeries"]
            a = _pick(sts[0]["areas"], sarea)
            for i, t in enumerate(sts[0]["timeDefines"]):
                d = t[:10]
                if d in rec:
                    rec[d]["code"] = int(a["weatherCodes"][i])
            a = _pick(sts[1]["areas"], sarea)
            now = datetime.now(JST)
            spop = {}
            for i, t in enumerate(sts[1]["timeDefines"]):
                slot = datetime.strptime(t[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=JST)
                v = _num(a["pops"][i])
                if v is not None and slot + timedelta(hours=6) > now:
                    spop[t[:10]] = max(spop.get(t[:10], 0), v)
            for d, v in spop.items():
                if d in rec and (d == days[0] or rec[d]["pop"] is None):
                    rec[d]["pop"] = v
            if len(sts) > 2:
                st = _pick(sts[2]["areas"], station)
                for i, t in enumerate(sts[2]["timeDefines"]):
                    d, hh = t[:10], t[11:13]
                    v = _num(st["temps"][i])
                    if d in rec and v is not None:
                        if hh == "09":
                            rec[d]["tmax"] = v
                        elif hh == "00" and d != days[0]:
                            rec[d]["tmin"] = v
            out[name] = [rec[d] for d in days]
        except Exception as e:
            print("jma NG", name, office, e, file=sys.stderr)
    return out


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
    # 気象庁の予報で上書き（取れた都市のみ）
    try:
        jma = fetch_jma()
        if jma:
            out.setdefault("weekly", {}).update(jma)
            print("jma OK", len(jma), "cities", file=sys.stderr)
    except Exception as e:
        print("jma NG", e, file=sys.stderr)
    try:
        r = _get_json({
            "latitude": CHIYODA[0], "longitude": CHIYODA[1],
            "hourly": "weather_code,temperature_2m,precipitation,precipitation_probability,"
                      "wind_speed_10m,wind_direction_10m,is_day",
            "wind_speed_unit": "ms", "timezone": "Asia/Tokyo", "forecast_days": 3,
            "models": "jma_seamless",
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


def jma_kinds(code):
    """気象庁コード → (主の天気, 副の天気 or None, つなぎ '時々'/'のち'/None, 表示名)"""
    c = int(code)
    label = TELOP.get(c)
    main = {1: "sun", 2: "cloud", 3: "rain", 4: "snow"}.get(c // 100, "cloud")
    if c == 209:
        return "fog", None, None, "霧"
    if not label:
        return main, None, None, {"sun": "晴れ", "cloud": "曇り", "rain": "雨", "snow": "雪"}[main]
    rest = label[2:] if label[:2] in ("晴れ", "曇り") else label[1:]
    if label.startswith("朝の内"):
        rest = label
    sub = None
    for w, k in (("雷", "thunder"), ("雪", "snow"), ("みぞれ", "snow"), ("雨", "rain"), ("晴", "sun"), ("曇", "cloud"), ("霧", "fog")):
        if w in rest and k != main:
            sub = k
            break
    conn = "のち" if ("のち" in label or "から" in label) else ("時々" if sub else None)
    return main, sub, conn, label


def _body(kind, day=True):
    if kind == "sun":
        return SUN if day else MOON
    if kind == "cloud":
        return CLOUD
    if kind == "fog":
        return CLOUD_DARK.replace("M18 44", "M18 40") + FOG
    if kind == "rain":
        return CLOUD_DARK + RAIN
    if kind == "snow":
        return CLOUD_DARK + SNOW
    if kind == "thunder":
        return CLOUD_DARK + BOLT
    return CLOUD


def icon_jma(code, size):
    """主の天気を左に大きく、副の天気を右下に。『のち』は矢印付き（横長アイコン）"""
    main, sub, conn, _ = jma_kinds(code)
    if not sub:
        return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 64 64">%s</svg>'
                % (size, size, _body(main)))
    w = int(size * 1.5)
    if conn == "のち":
        body = ('<g transform="translate(-4,0) scale(0.80)">%s</g>'
                '<g stroke="#6b788b" stroke-width="3" fill="none" stroke-linecap="round">'
                '<path d="M44 50h10"/><path d="M50 45l5 5-5 5"/></g>'
                '<g transform="translate(56,22) scale(0.62)">%s</g>') % (_body(main), _body(sub))
    else:
        body = ('<g transform="translate(-2,-2) scale(0.85)">%s</g>'
                '<g transform="translate(50,24) scale(0.62)">%s</g>') % (_body(main), _body(sub))
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 96 64">%s</svg>'
            % (w, size, body))


def icon_any(d, size):
    return icon_jma(d["code"], size) if d.get("jma") and d.get("code") else icon(d.get("code"), size)


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
                % (cls, icon_any(d, 58), _r(d["tmax"]), _r(d["tmin"]), pop))
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
    """全国天気マップ（今日の天気）"""
    if not weekly:
        return '<div class="wx-empty">天気データを取得できませんでした</div>', ""
    now = datetime.now(JST)
    idx = 0  # 常に今日の天気（タイトルに日付を出さないため、明日への切り替えはしない）
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
            % (cx, cy, name, icon_any(d, 60), _r(d["tmax"]), _r(d["tmin"]), pop))
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
