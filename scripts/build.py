# -*- coding: utf-8 -*-
"""
マーケット情報サイネージ用 index.html を生成するスクリプト
（GitHub Actions から定期実行。Python標準ライブラリのみ使用）

- 相場データを取得 → 数値を直接書き込んだ静的HTMLを出力
- 取得に失敗した銘柄は前回値（data.json）を使うので、画面が空欄になりません
- STBの古いブラウザでも表示できるよう、HTML/CSSは table と基本的な指定のみ
"""
import csv
import io
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(ROOT, "data.json")
OUT_PATH = os.path.join(ROOT, "index.html")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# key: (Yahoo Financeのシンボル候補, Stooqのシンボル)
ITEMS = {
    "usdjpy": (["JPY=X"], "usdjpy"),
    "eurjpy": (["EURJPY=X"], "eurjpy"),
    "dji":    (["^DJI"], "^dji"),
    "ixic":   (["^IXIC"], "^ndq"),
    "n225":   (["^N225"], "^nkx"),
    "topix":  (["^TOPX", "^TPX", "998405.T"], "^tpx"),
}


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")


def from_yahoo(sym):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + urllib.request.quote(sym) + "?range=1d&interval=1d")
    meta = json.loads(http_get(url))["chart"]["result"][0]["meta"]
    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    if price is None or prev is None:
        raise ValueError("no price")
    return float(price), float(prev)


def from_stooq(sym):
    url = "https://stooq.com/q/d/l/?s=" + urllib.request.quote(sym) + "&i=d"
    rows = [r for r in csv.DictReader(io.StringIO(http_get(url))) if r.get("Close")]
    if len(rows) < 2:
        raise ValueError("no data")
    return float(rows[-1]["Close"]), float(rows[-2]["Close"])


def _num(x):
    return float(x.replace(",", "").replace("+", ""))


def from_yahoo_jp(code):
    """Yahoo!ファイナンス（日本）のページから現在値と前日比を読む"""
    html = http_get("https://finance.yahoo.co.jp/quote/" + code)
    m = re.search(r'"price":"([\d,\.]+)"', html)
    c = re.search(r'"priceChange":"([-+]?[\d,\.]+)"', html) or \
        re.search(r'"changePrice":"([-+]?[\d,\.]+)"', html)
    if not m or not c:
        raise ValueError("pattern not found")
    price = _num(m.group(1))
    return price, price - _num(c.group(1))


def from_google(q):
    """Google Finance のページから現在値と前日終値を読む"""
    html = http_get("https://www.google.com/finance/quote/" + q + "?hl=en")
    m = re.search(r'data-last-price="([\d\.]+)"', html)
    pc = re.search(r'Previous close</div>.*?>([\d,]+\.\d+)<', html, re.S)
    if not m or not pc:
        raise ValueError("pattern not found")
    return float(m.group(1)), _num(pc.group(1))


# 追加の取得先（Yahoo/Stooqで取れない銘柄用）
EXTRA = {
    "topix": [lambda: from_yahoo_jp("998405.T"),
              lambda: from_google("TOPIX:INDEXTOKYO")],
}


def fetch(key):
    ysyms, ssym = ITEMS[key]
    for i, f in enumerate(EXTRA.get(key, [])):
        try:
            r = f()
            print("extra OK", key, i, r, file=sys.stderr)
            return r
        except Exception as e:
            print("extra NG", key, i, e, file=sys.stderr)
    for s in ysyms:
        try:
            return from_yahoo(s)
        except Exception as e:
            print("yahoo NG", key, s, e, file=sys.stderr)
    try:
        return from_stooq(ssym)
    except Exception as e:
        print("stooq NG", key, ssym, e, file=sys.stderr)
    return None


# ---------- 表示用の整形（テレビ風：円・銭 / ドル・セント） ----------
def comma(n):
    return "{:,}".format(n)


def split2(v):
    """小数第2位までで整数部・小数部に分ける"""
    cents = int(round(abs(v) * 100))
    return cents // 100, cents % 100


def fmt_fx(v):
    y, s = split2(v)
    return '%s<span class="u">円</span>%02d<span class="u">銭</span>' % (y, s)


def fmt_yen_index(v):
    y, s = split2(v)
    if y >= 10000:
        big = '%d<span class="u">万</span>%s' % (y // 10000, comma(y % 10000))
    else:
        big = comma(y)
    return '%s<span class="u">円</span>%02d<span class="u">銭</span>' % (big, s)


def fmt_yen_diff(v):
    y, s = split2(v)
    return '%s<span class="u">円</span>%02d<span class="u">銭</span>' % (comma(y), s)


def fmt_usd(v):
    d, c = split2(v)
    return '%s<span class="u">ドル</span>%02d<span class="u">セント</span>' % (comma(d), c)


def fmt_pt(v, digits=2):
    return "{:,.{d}f}".format(abs(v), d=digits)


def badge(diff):
    if diff > 0:
        return '<span class="up">&#9650;株高</span>'
    if diff < 0:
        return '<span class="dn">&#9660;株安</span>'
    return '<span class="fl">変わらず</span>'


def fx_diff(diff):
    y, s = split2(diff)
    arrow = "円安" if diff > 0 else ("円高" if diff < 0 else "変わらず")
    cls = "dn" if diff > 0 else ("up" if diff < 0 else "fl")
    return '前日比 %s%d銭 <span class="%s">%s</span>' % ("+" if diff > 0 else ("-" if diff < 0 else "±"), y * 100 + s, cls, arrow)


def main():
    try:
        with open(DATA_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}

    now = datetime.now(JST)
    for k in ITEMS:
        r = fetch(k)
        if r:
            data[k] = {"price": r[0], "prev": r[1], "at": now.strftime("%Y-%m-%d %H:%M")}

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    def cell(key, main_fmt, diff_fmt):
        d = data.get(key)
        if not d:
            return '<div class="val">―</div><div class="chg">&nbsp;</div>'
        diff = d["price"] - d["prev"]
        return '<div class="val">%s</div><div class="chg">%s</div>' % (main_fmt(d["price"]), diff_fmt(diff))

    html = TEMPLATE
    repl = {
        "{{USDJPY}}": cell("usdjpy", fmt_fx, fx_diff),
        "{{EURJPY}}": cell("eurjpy", fmt_fx, fx_diff),
        "{{DJI}}":    cell("dji", fmt_usd, lambda x: fmt_usd(x) + " " + badge(x)),
        "{{IXIC}}":   cell("ixic", lambda v: fmt_pt(v, 3), lambda x: fmt_pt(x, 3) + " " + badge(x)),
        "{{N225}}":   cell("n225", fmt_yen_index, lambda x: fmt_yen_diff(x) + " " + badge(x)),
        "{{TOPIX}}":  cell("topix", fmt_pt, lambda x: fmt_pt(x) + " " + badge(x)),
        "{{UPDATED}}": now.strftime("%m/%d %H:%M"),
    }
    for a, b in repl.items():
        html = html.replace(a, b)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print("built", OUT_PATH)


TEMPLATE = u"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=1920">
<meta http-equiv="refresh" content="600">
<title>マーケット情報</title>
<style>
html,body{margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:#c9d8f0;}
body{font-family:"Noto Sans JP","Noto Sans CJK JP","Meiryo","Hiragino Sans",sans-serif;}
#stage{position:absolute;left:0;top:0;width:1920px;height:1080px;
  background:#d3e0f5;-webkit-transform-origin:0 0;transform-origin:0 0;}
#clock{position:absolute;left:70px;top:25px;font-size:120px;font-weight:bold;color:#e0357f;line-height:1.1;}
#date{position:absolute;right:80px;top:60px;font-size:48px;font-weight:bold;color:#1a2a6c;}
table.b{position:absolute;left:60px;top:175px;width:1800px;border-collapse:separate;border-spacing:24px 12px;table-layout:fixed;}
td{vertical-align:top;padding:0;}
.h{background:#1f2fb8;color:#fff;text-align:center;font-size:56px;font-weight:bold;letter-spacing:8px;height:84px;vertical-align:middle;}
.blank{background:transparent;}
.card{background:#fff;height:320px;position:relative;overflow:hidden;}
.lb{display:inline-block;margin:18px 0 0 18px;background:#1f2fb8;color:#fff;font-size:36px;font-weight:bold;padding:4px 18px;}
.val{font-size:70px;font-weight:bold;color:#111;text-align:center;margin-top:22px;white-space:nowrap;letter-spacing:1px;}
.chg{font-size:40px;font-weight:bold;color:#222;text-align:right;margin:14px 30px 0 0;white-space:nowrap;}
.u{font-size:0.5em;margin:0 4px;}
.up,.dn,.fl{display:inline-block;font-size:30px;color:#fff;padding:2px 10px;margin-left:8px;vertical-align:middle;}
.up{background:#e0302a;} .dn{background:#1f6fe0;} .fl{background:#777;}
#note{position:absolute;right:84px;bottom:6px;font-size:20px;color:#334;}
</style>
</head>
<body>
<div id="stage">
 <div id="clock">--:--</div>
 <div id="date"></div>
 <table class="b">
  <tr>
   <td class="blank"></td>
   <td class="h">ニューヨーク市場</td>
   <td class="h">東京株式市場</td>
  </tr>
  <tr>
   <td class="h">為　替</td>
   <td class="h">株　価</td>
   <td class="h">株　価</td>
  </tr>
  <tr>
   <td><div class="card"><span class="lb">1ドル</span>{{USDJPY}}</div></td>
   <td><div class="card"><span class="lb">ダウ平均</span>{{DJI}}</div></td>
   <td><div class="card"><span class="lb">日経平均株価</span>{{N225}}</div></td>
  </tr>
  <tr>
   <td><div class="card"><span class="lb">1ユーロ</span>{{EURJPY}}</div></td>
   <td><div class="card"><span class="lb">ナスダック</span>{{IXIC}}</div></td>
   <td><div class="card"><span class="lb">東証株価指数（TOPIX）</span>{{TOPIX}}</div></td>
  </tr>
 </table>
 <div id="note">データ更新 {{UPDATED}}　※株価は遅延値・NY市場は前営業日終値　参考情報であり正確性を保証するものではありません</div>
</div>
<script>
function fit(){
  var w=window.innerWidth||document.documentElement.clientWidth;
  var h=window.innerHeight||document.documentElement.clientHeight;
  var k=Math.min(w/1920,h/1080);
  var st=document.getElementById('stage');
  var t='scale('+k+')';
  st.style.webkitTransform=t; st.style.transform=t;
  st.style.left=((w-1920*k)/2)+'px'; st.style.top=((h-1080*k)/2)+'px';
}
function p2(n){return (n<10?'0':'')+n;}
function tick(){
  var d=new Date();
  document.getElementById('clock').innerHTML=d.getHours()+':'+p2(d.getMinutes());
  document.getElementById('date').innerHTML=(d.getMonth()+1)+'月'+d.getDate()+'日（'+'日月火水木金土'.charAt(d.getDay())+'）';
}
window.onresize=fit; fit(); tick(); setInterval(tick,5000);
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
