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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import weather  # noqa: E402

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
    "us10y":  (["^TNX"], "10usy.b"),
    "jp10y":  ([], "10jpy.b"),
}


def http_bytes(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def http_get(url):
    return http_bytes(url).decode("utf-8", "replace")


def from_mof(col="10年"):
    """財務省『国債金利情報』CSV（公式・1日1回更新）から10年利回りを読む"""
    base = "https://www.mof.go.jp/jgbs/reference/interest_rate/"
    vals = []
    for name in ("jgbcm.csv", "historical/jgbcm_all.csv", "data/jgbcm_all.csv"):
        try:
            text = http_bytes(base + name).decode("cp932", "replace")
        except Exception as e:
            print("mof NG", name, e, file=sys.stderr)
            continue
        rows = list(csv.reader(io.StringIO(text)))
        hdr = next((i for i, r in enumerate(rows) if r and r[0].strip() == "基準日"), None)
        if hdr is None or col not in rows[hdr]:
            continue
        ci = rows[hdr].index(col)
        vals = [r[ci] for r in rows[hdr + 1:] if len(r) > ci]
        vals = [float(v) for v in vals if re.match(r"^-?\d+(\.\d+)?$", v.strip())]
        if len(vals) >= 2:
            return vals[-1], vals[-2]
    raise ValueError("mof csv not usable")


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
    "jp10y": [from_mof],
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


def fmt_rate(v):
    return '%.3f<span class="u">%%</span>' % v


def rate_diff(diff):
    if diff > 0:
        b = '<span class="up">&#9650;上昇</span>'
    elif diff < 0:
        b = '<span class="dn">&#9660;低下</span>'
    else:
        b = '<span class="fl">変わらず</span>'
    return '%s%.3f %s' % ("+" if diff > 0 else ("-" if diff < 0 else "±"), abs(diff), b)


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

    wx = weather.fetch_weather()
    wdata = data.get("weather") or {}
    for k in ("weekly", "hourly"):
        if wx.get(k):
            wdata[k] = wx[k]
            wdata["at"] = now.strftime("%m/%d %H:%M")
    data["weather"] = wdata

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    def cell(key, main_fmt, diff_fmt):
        d = data.get(key)
        if not d:
            return '<div class="val">―</div><div class="chg">&nbsp;</div>'
        diff = d["price"] - d["prev"]
        return '<div class="val">%s</div><div class="chg">%s</div>' % (main_fmt(d["price"]), diff_fmt(diff))

    def rate(key):
        d = data.get(key)
        if not d:
            return '<div class="rc">&nbsp;</div></td><td class="rv">―</td>'
        return '<div class="rc">%s</div></td><td class="rv">%s</td>' % (rate_diff(d["price"] - d["prev"]), fmt_rate(d["price"]))

    map_html, map_label = weather.render_map(wdata.get("weekly"))
    html = TEMPLATE
    repl = {
        "{{USDJPY}}": cell("usdjpy", fmt_fx, fx_diff),
        "{{EURJPY}}": cell("eurjpy", fmt_fx, fx_diff),
        "{{DJI}}":    cell("dji", fmt_usd, lambda x: fmt_usd(x) + " " + badge(x)),
        "{{IXIC}}":   cell("ixic", lambda v: fmt_pt(v, 3), lambda x: fmt_pt(x, 3) + " " + badge(x)),
        "{{N225}}":   cell("n225", fmt_yen_index, lambda x: fmt_yen_diff(x) + " " + badge(x)),
        "{{TOPIX}}":  cell("topix", fmt_pt, lambda x: fmt_pt(x) + " " + badge(x)),
        "{{JP10Y}}":  rate("jp10y"),
        "{{US10Y}}":  rate("us10y"),
        "{{UPDATED}}": now.strftime("%m/%d %H:%M"),
        "{{WEEK_E}}": weather.render_weekly(wdata.get("weekly"), weather.EAST, "東日本"),
        "{{WEEK_W}}": weather.render_weekly(wdata.get("weekly"), weather.WEST, "西日本"),
        "{{HOURLY}}": weather.render_hourly(wdata.get("hourly")),
        "{{MAP}}": map_html,
        "{{MAP_LABEL}}": map_label,
        "{{WX_UPDATED}}": wdata.get("at", "―"),
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
<meta http-equiv="refresh" content="1800">
<title>マーケット情報</title>
<style>
html,body{margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:#c9d8f0;}
body{font-family:"Noto Sans JP","Noto Sans CJK JP","Meiryo","Hiragino Sans",sans-serif;}
#stage{position:absolute;left:0;top:0;width:1920px;height:1080px;
  background:#d3e0f5;-webkit-transform-origin:0 0;transform-origin:0 0;}
#clock{position:absolute;left:70px;top:25px;font-size:120px;font-weight:bold;color:#e0357f;line-height:1.1;}
#logo{position:absolute;right:80px;top:24px;}
#logo img{height:56px;display:block;}
#date{position:absolute;right:80px;top:92px;font-size:48px;font-weight:bold;color:#1a2a6c;}
table.b{position:absolute;left:60px;top:160px;width:1800px;border-collapse:separate;border-spacing:24px 10px;table-layout:fixed;}
td{vertical-align:top;padding:0;}
.h{background:#1f2fb8;color:#fff;text-align:center;font-size:50px;font-weight:bold;letter-spacing:8px;height:72px;vertical-align:middle;}
.blank{background:transparent;}
.card{background:#fff;height:262px;position:relative;overflow:hidden;}
.lb{display:inline-block;margin:14px 0 0 16px;background:#1f2fb8;color:#fff;font-size:32px;font-weight:bold;padding:4px 18px;}
.val{font-size:66px;font-weight:bold;color:#111;text-align:center;margin-top:10px;white-space:nowrap;letter-spacing:1px;}
.chg{font-size:38px;font-weight:bold;color:#222;text-align:right;margin:6px 30px 0 0;white-space:nowrap;}
.u{font-size:0.5em;margin:0 4px;}
.up,.dn,.fl{display:inline-block;font-size:30px;color:#fff;padding:2px 10px;margin-left:8px;vertical-align:middle;}
.up{background:#e0302a;} .dn{background:#1f6fe0;} .fl{background:#777;}
.rate{background:#fff;height:128px;}
.rate table{width:100%;height:128px;border-collapse:collapse;}
.rl{width:1%;padding:0 0 0 16px;vertical-align:middle;white-space:nowrap;}
.rl span{display:inline-block;background:#1f2fb8;color:#fff;font-size:30px;font-weight:bold;padding:4px 14px;}
.rc{font-size:30px;font-weight:bold;color:#222;margin-top:12px;white-space:nowrap;}
.rc .up,.rc .dn,.rc .fl{font-size:26px;}
.rv{font-size:72px;font-weight:bold;color:#111;text-align:right;padding-right:36px;vertical-align:middle;white-space:nowrap;}
#note,.note{position:absolute;right:84px;bottom:6px;font-size:20px;color:#334;}
.slide{display:none;}
#ttl{position:absolute;left:380px;width:1100px;top:52px;text-align:center;font-size:52px;font-weight:bold;color:#1a2a6c;letter-spacing:4px;}
#pg{position:absolute;left:84px;bottom:12px;}
#pg span{display:inline-block;width:16px;height:16px;border-radius:8px;background:#9fb3d9;margin-right:10px;}
#pg span.on{background:#1f2fb8;}
table.wk{position:absolute;left:60px;top:170px;width:1800px;border-collapse:separate;border-spacing:4px;table-layout:fixed;}
table.wk th{height:64px;background:#1f2fb8;color:#fff;font-size:34px;font-weight:bold;vertical-align:middle;}
table.wk th span{font-size:26px;}
table.wk th.wc{width:200px;font-size:30px;background:#3c4a8f;}
table.wk th.sat{background:#2f6fd6;} table.wk th.sun{background:#d9463d;}
td.wn{height:74px;background:#1f2fb8;color:#fff;font-size:36px;font-weight:bold;text-align:center;vertical-align:middle;}
td.wv{background:#fff;vertical-align:middle;}
td.wv.sat{background:#eef4ff;} td.wv.sun{background:#fff1f0;}
table.wi{width:100%;border-collapse:collapse;}
table.wi td.ic{width:64px;padding-left:10px;vertical-align:middle;}
table.wi td.ic svg{display:block;}
table.wi td.tt{text-align:center;vertical-align:middle;white-space:nowrap;font-weight:bold;}
.hi{font-size:34px;color:#d9302a;} .lo{font-size:34px;color:#1f5fd0;} .sl{font-size:28px;color:#888;margin:0 4px;}
.pp{font-size:22px;color:#1f5fd0;line-height:1.1;}
#hgrid{position:absolute;left:60px;top:175px;width:1800px;text-align:center;}
.hc{display:none;width:282px;height:410px;margin:0 6px 14px 6px;background:#fff;text-align:center;vertical-align:top;overflow:hidden;}
.hd{font-size:24px;color:#667;margin-top:8px;line-height:1.2;}
.ht{font-size:46px;font-weight:bold;color:#1a2a6c;line-height:1.1;}
.hi2 svg{display:block;margin:2px auto 0 auto;}
.hl{font-size:28px;font-weight:bold;color:#333;line-height:1.2;}
.hT{font-size:54px;font-weight:bold;color:#111;line-height:1.15;}
.hT span,.hr span,.hw span{font-size:0.55em;margin-left:2px;}
.hr{font-size:26px;font-weight:bold;color:#1f5fd0;line-height:1.3;}
.hw{font-size:26px;font-weight:bold;color:#445;line-height:1.3;}
.jmap{position:absolute;left:0;top:0;width:1920px;height:1080px;}
.mc{position:absolute;width:150px;height:140px;background:#fff;text-align:center;border-radius:8px;
  box-shadow:0 3px 8px rgba(0,40,90,0.25);overflow:hidden;}
.mn{font-size:26px;font-weight:bold;color:#1a2a6c;line-height:1.25;margin-top:2px;}
.mc svg{display:block;margin:-2px auto 0 auto;}
.mt{line-height:1.0;white-space:nowrap;font-weight:bold;}
.mt .hi,.mt .lo{font-size:30px;}
.mp{font-size:22px;font-weight:bold;color:#1f5fd0;line-height:1.3;}
.wx-empty{position:absolute;left:0;width:1920px;top:480px;text-align:center;font-size:48px;color:#556;}
</style>
</head>
<body>
<div id="stage">
 <div id="clock">--:--</div>
 <div id="logo"><img src="logo.png" alt="青山メインランド"></div>
 <div id="date"></div>
 <div id="ttl"></div>
 <div class="slide" id="s0">
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
  <tr>
   <td class="h" style="height:128px;">金　利</td>
   <td><div class="rate"><table><tr><td class="rl"><span>日本10年国債</span>{{JP10Y}}</tr></table></div></td>
   <td><div class="rate"><table><tr><td class="rl"><span>米国10年国債</span>{{US10Y}}</tr></table></div></td>
  </tr>
 </table>
 <div id="note">データ更新 {{UPDATED}}　※株価は遅延値・NY市場は前営業日終値・日本国債は財務省公表の前営業日値　参考情報であり正確性を保証するものではありません</div>
 </div>
 <div class="slide" id="s1">
  <div id="wkA">{{WEEK_E}}</div>
  <div id="wkB" style="display:none;">{{WEEK_W}}</div>
  <div class="note">予報取得 {{WX_UPDATED}}　Weather data by Open-Meteo.com（気象庁ほかの数値予報モデル）　最高／最低気温℃・&#9730;降水確率</div>
 </div>
 <div class="slide" id="s2">
  {{HOURLY}}
  <div class="note">予報取得 {{WX_UPDATED}}　Weather data by Open-Meteo.com（気象庁ほかの数値予報モデル）　&#9730;1時間降水量・降水確率／風向・風速</div>
 </div>
 <div class="slide" id="s3">
  {{MAP}}
  <div class="note">予報取得 {{WX_UPDATED}}　Weather data by Open-Meteo.com　地図：国土地理院「地球地図日本」をもとに作成　最高／最低気温℃・&#9730;降水確率</div>
 </div>
 <div id="pg"><span></span><span></span><span></span><span></span><span></span></div>
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
/* ---- 画面切り替え：マーケット4分 → 週間天気3分（東1分半・西1分半）→ 1時間天気3分 ---- */
var CYCLE=600, lastPos=-1, lastIdx=-1;
var ORDER=['s0','s1','s1','s3','s2'];
var TITLES=['','週間天気予報','週間天気予報','全国の天気　{{MAP_LABEL}}','千代田区　1時間ごとの天気予報'];
function $(id){return document.getElementById(id);}
function showHourly(){
  var g=$('hgrid'); if(!g) return;
  var cs=g.getElementsByTagName('div'), now=Math.floor(new Date().getTime()/3600000)*3600, n=0, i;
  for(i=0;i<cs.length;i++){
    if(cs[i].className!=='hc') continue;
    var t=parseInt(cs[i].getAttribute('data-t'),10);
    if(t>=now && n<12){cs[i].style.display='inline-block'; n++;} else {cs[i].style.display='none';}
  }
}
function safeReload(){
  var base=location.href.split('?')[0], x;
  try{
    x=new XMLHttpRequest();
    x.open('GET',base+'?chk='+new Date().getTime(),true);
    x.onreadystatechange=function(){
      if(x.readyState===4 && x.status===200){ location.replace(base+'?t='+new Date().getTime()); }
    };
    x.send(null);
  }catch(e){}
}
function rotate(){
  var pos=Math.floor(new Date().getTime()/1000)%CYCLE;
  if(lastPos>=0 && pos<lastPos){ safeReload(); }
  lastPos=pos;
  var idx=Math.floor(pos/120), i;
  if(idx>4) idx=4;
  if(idx!==lastIdx){
    var sl=['s0','s1','s2','s3'];
    for(i=0;i<sl.length;i++){ $(sl[i]).style.display=(sl[i]===ORDER[idx])?'block':'none'; }
    var dots=$('pg').getElementsByTagName('span');
    for(i=0;i<dots.length;i++){ dots[i].className=(i===idx)?'on':''; }
    if(idx===4) showHourly();
    lastIdx=idx;
  }
  if(idx===1||idx===2){
    var east=(idx===1);
    $('wkA').style.display=east?'block':'none';
    $('wkB').style.display=east?'none':'block';
    $('ttl').innerHTML=TITLES[1]+'<span style="font-size:40px;">　'+(east?'東日本':'西日本')+'</span>';
  } else {
    $('ttl').innerHTML=TITLES[idx];
  }
}
window.onresize=fit; fit(); tick(); rotate(); setInterval(tick,5000); setInterval(rotate,1000);
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
