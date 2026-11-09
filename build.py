#!/usr/bin/env python3
"""Kindle Lab — morning dashboard builder.

Fetches weather, stocks, next SpaceX launch, headlines, and a daily public-domain
B&W photo, then renders a self-contained static index.html (data baked in) plus a
data.json. Designed to run locally or from a scheduled GitHub Action.
Only third-party dependency: Pillow. Everything else is stdlib.
"""
import os, sys, io, json, html, urllib.request, urllib.parse
from datetime import datetime, timezone
from xml.etree import ElementTree as ET
from string import Template
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None
from PIL import Image, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
UA = "KindleLabBot/1.0 (personal e-reader dashboard)"

def _get(url, timeout=25, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def _get_json(url, **kw):
    return json.loads(_get(url, **kw).decode("utf-8", "replace"))

def esc(s):
    return html.escape("" if s is None else str(s))

WMO = {0:"Clear",1:"Mainly clear",2:"Partly cloudy",3:"Overcast",45:"Fog",48:"Fog",
       51:"Light drizzle",53:"Drizzle",55:"Heavy drizzle",56:"Freezing drizzle",57:"Freezing drizzle",
       61:"Light rain",63:"Rain",65:"Heavy rain",66:"Freezing rain",67:"Freezing rain",
       71:"Light snow",73:"Snow",75:"Heavy snow",77:"Snow grains",
       80:"Light showers",81:"Showers",82:"Heavy showers",85:"Snow showers",86:"Snow showers",
       95:"Thunderstorm",96:"Thunderstorm, hail",99:"Thunderstorm, hail"}
def wmo(c):
    try: return WMO.get(int(c), "—")
    except Exception: return "—"

CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
LOC = CFG["location"]
TZNAME = LOC.get("timezone", "UTC")
TZ = ZoneInfo(TZNAME) if ZoneInfo else timezone.utc
NOW = datetime.now(TZ)

def fetch_weather():
    u = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
         "&current=temperature_2m,apparent_temperature,weather_code"
         "&daily=temperature_2m_max,temperature_2m_min,weather_code"
         "&timezone=%s&forecast_days=3") % (LOC["latitude"], LOC["longitude"], urllib.parse.quote(TZNAME))
    d = _get_json(u)
    cur, daily = d["current"], d["daily"]
    out = {"temp": round(cur["temperature_2m"]), "feels": round(cur["apparent_temperature"]),
           "cond": wmo(cur["weather_code"]),
           "today_hi": round(daily["temperature_2m_max"][0]),
           "today_lo": round(daily["temperature_2m_min"][0]), "days": []}
    for i in (1, 2):
        dt = datetime.fromisoformat(daily["time"][i])
        out["days"].append({"label": dt.strftime("%a %-d"), "cond": wmo(daily["weather_code"][i]),
                            "hi": round(daily["temperature_2m_max"][i]),
                            "lo": round(daily["temperature_2m_min"][i])})
    return out

def fetch_stocks():
    out = []
    for sym in CFG["tickers"]:
        try:
            u = "https://query1.finance.yahoo.com/v8/finance/chart/%s?interval=1d&range=5d" % urllib.parse.quote(sym)
            res = _get_json(u)["chart"]["result"][0]
            m = res["meta"]
            price = m.get("regularMarketPrice")
            # NB: with range=5d, meta.chartPreviousClose is the close *before the 5-day window*,
            # not yesterday's close. Use the second-to-last daily close from the series instead.
            closes = [c for c in ((res.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
                      if c is not None]
            prev = closes[-2] if len(closes) >= 2 else None
            if price is None and closes:
                price = closes[-1]
            chg = (price - prev) if (price is not None and prev) else None
            pct = (chg / prev * 100) if (chg is not None and prev) else None
            out.append({"sym": sym, "name": (m.get("shortName") or m.get("longName") or sym).strip(),
                        "price": price, "chg": chg, "pct": pct})
        except Exception as e:
            sys.stderr.write("stock %s failed: %s\n" % (sym, e))
            out.append({"sym": sym, "name": sym, "price": None, "chg": None, "pct": None})
    return out

def _countdown(dt_utc):
    secs = (dt_utc - datetime.now(timezone.utc)).total_seconds()
    if secs < 0: return "imminent"
    h = int(secs // 3600)
    return ("in ~%d hours" % h) if h < 48 else ("in ~%d days" % (h // 24))

def fetch_launch():
    base = os.environ.get("LL_BASE", "https://ll.thespacedevs.com")
    u = base + "/2.2.0/launch/upcoming/?search=SpaceX&limit=1"
    r = _get_json(u, timeout=30)["results"][0]
    net = r.get("net")
    dt = datetime.fromisoformat(net.replace("Z", "+00:00")) if net else None
    local = dt.astimezone(TZ) if dt else None
    pad = r.get("pad") or {}
    return {"name": r.get("name"), "status": (r.get("status") or {}).get("name") or "",
            "pad": (pad.get("location") or {}).get("name") or pad.get("name") or "",
            "when": local.strftime("%a %-d %b, %-I:%M %p") if local else "TBD",
            "countdown": _countdown(dt) if dt else ""}

def fetch_news():
    out, n = [], CFG.get("headlines_per_topic", 1)
    for t in CFG["news"]:
        try:
            u = "https://news.google.com/rss/search?q=%s&hl=en-AU&gl=AU&ceid=AU:en" % urllib.parse.quote(t["query"])
            root = ET.fromstring(_get(u, timeout=25))
            items = root.findall(".//item")[:n]
            heads = []
            for it in items:
                title = (it.findtext("title") or "").strip()
                heads.append(title.rsplit(" - ", 1)[0] if " - " in title else title)
            out.append({"tag": t["tag"], "items": heads})
        except Exception as e:
            sys.stderr.write("news %s failed: %s\n" % (t["tag"], e))
            out.append({"tag": t["tag"], "items": []})
    return out

def fetch_photo():
    photos = json.load(open(os.path.join(HERE, "photos.json"), encoding="utf-8"))
    assets = os.path.join(HERE, "assets")
    os.makedirs(os.path.join(assets, "_src"), exist_ok=True)
    start = NOW.toordinal() % len(photos)
    order = list(range(start, len(photos))) + list(range(0, start))
    for i in order:
        p = photos[i]
        try:
            raw = _get(p["url"], timeout=45)
            im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("L")  # grayscale (treatment A)
            w = 1272; h = round(w * im.height / im.width)
            im = ImageOps.autocontrast(im.resize((w, h), Image.LANCZOS), cutoff=1)
            im.save(os.path.join(assets, "photo.jpg"), quality=88)
            return {"photographer": p["photographer"], "title": p["title"],
                    "year": p.get("year", ""), "credit": p.get("credit", "")}
        except Exception as e:
            sys.stderr.write("photo '%s' failed: %s\n" % (p.get("title"), e))
    return None  # keep any existing photo.jpg

# ---------- rendering ----------
def r_forecast(days):
    cells = ""
    for d in days:
        cells += ('<div><div class="fd">%s</div><div class="fw">%s</div>'
                  '<div class="ft">%s&deg; / %s&deg;</div></div>') % (esc(d["label"]), esc(d["cond"]), d["hi"], d["lo"])
    return cells

def r_markets(stocks):
    rows = ""
    for s in stocks:
        if s["price"] is None:
            px, chg = "&mdash;", '<td class="chg">n/a</td>'
        else:
            px = "$%.2f" % s["price"]
            if s["chg"] is None:
                chg = '<td class="chg">&mdash;</td>'
            else:
                cls = "dn" if s["chg"] < 0 else "up"
                pct = ("%.2f%%" % abs(s["pct"])) if s["pct"] is not None else ""
                chg = '<td class="chg %s">%s %+.2f</td>' % (cls, pct, s["chg"])
        rows += ('<tr><td class="sym">%s<span class="nm">%s</span></td>'
                 '<td class="px">%s</td>%s</tr>') % (esc(s["sym"]), esc(s["name"]), px, chg)
    return rows

def r_headlines(news):
    parts = []
    for t in news:
        head = t["items"][0] if t["items"] else "— no headline —"
        parts.append('<div class="hd"><div class="tag">%s</div><div class="ttl">%s</div></div>'
                     % (esc(t["tag"]), esc(head)))
    return '<hr class="thin">'.join(parts)

TEMPLATE = Template(r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Morning Dashboard</title>
<style>
 *{box-sizing:border-box;}
 body{background:#fff;color:#000;margin:0;padding:22px 20px 40px;font-family:Helvetica,Arial,sans-serif;max-width:636px;}
 .mast{display:flex;justify-content:space-between;align-items:flex-end;}
 .greet{font-size:14px;letter-spacing:3px;text-transform:uppercase;}
 .bigdate{font-size:38px;font-weight:800;line-height:1.04;margin-top:3px;}
 .loc{font-size:14px;letter-spacing:2px;text-transform:uppercase;margin-top:6px;}
 .wx{text-align:right;}
 .wx .t{font-size:46px;font-weight:800;line-height:1;}
 .wx .c{font-size:15px;margin-top:2px;}
 .wx .hl{font-size:14px;margin-top:2px;}
 hr.big{border:0;border-top:4px solid #000;margin:14px 0 0;}
 hr.thin{border:0;border-top:1px solid #000;margin:0;}
 h2{font-size:13px;letter-spacing:4px;text-transform:uppercase;margin:22px 0 8px;font-weight:700;}
 .fc{display:flex;gap:10px;}
 .fc div{flex:1;border:1px solid #000;padding:8px;text-align:center;}
 .fc .fd{font-size:13px;text-transform:uppercase;letter-spacing:1px;}
 .fc .fw{font-size:13px;margin:4px 0;min-height:2.4em;}
 .fc .ft{font-size:16px;font-weight:700;}
 table.mkt{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;}
 table.mkt td{padding:9px 2px;border-bottom:1px solid #000;font-size:18px;vertical-align:middle;}
 table.mkt .sym{font-weight:800;}
 table.mkt .nm{font-size:12px;font-weight:400;display:block;letter-spacing:.3px;}
 table.mkt .px{text-align:right;font-weight:700;white-space:nowrap;}
 table.mkt .chg{text-align:right;white-space:nowrap;font-size:15px;padding-left:10px;}
 .dn::before{content:"\25BC  ";}
 .up::before{content:"\25B2  ";}
 .lau{border:2px solid #000;padding:14px;display:flex;justify-content:space-between;align-items:center;}
 .lau .ln{font-size:18px;font-weight:800;}
 .lau .lp{font-size:13px;margin-top:3px;letter-spacing:.3px;}
 .lau .lt{text-align:right;white-space:nowrap;padding-left:10px;}
 .lau .lt .lw{font-size:20px;font-weight:800;}
 .lau .lt .ls{font-size:12px;text-transform:uppercase;letter-spacing:1px;}
 .hd{margin:10px 0;}
 .hd .tag{font-size:11px;letter-spacing:2px;text-transform:uppercase;}
 .hd .ttl{font-size:17px;font-weight:600;line-height:1.3;}
 .photo{border:1px solid #000;}
 .photo img{display:block;width:100%;height:auto;}
 .cap{font-family:Georgia,serif;font-size:14px;padding:8px 2px 0;font-style:italic;}
 .cap b{font-style:normal;}
 .foot{margin-top:26px;border-top:1px solid #000;padding-top:8px;font-size:12px;letter-spacing:1px;text-transform:uppercase;display:flex;justify-content:space-between;}
</style>
</head>
<body>
 <div class="mast">
  <div>
   <div class="greet">$greet</div>
   <div class="bigdate">$bigdate</div>
   <div class="loc">$loc</div>
  </div>
  <div class="wx">
   <div class="t">$temp&deg;</div>
   <div class="c">$cond &middot; feels $feels&deg;</div>
   <div class="hl">Today $hi&deg; / $lo&deg;</div>
  </div>
 </div>
 <hr class="big">

 <h2>Next 2 days</h2>
 <div class="fc">$forecast</div>

 <h2>Markets &middot; at last close</h2>
 <table class="mkt">$markets</table>

 <h2>Next SpaceX launch</h2>
 <div class="lau">
  <div><div class="ln">$launch_name</div><div class="lp">$launch_pad</div></div>
  <div class="lt"><div class="lw">$launch_when</div><div class="ls">$launch_cd</div></div>
 </div>

 <h2>Headlines</h2>
 $headlines

 <h2>Photograph of the day</h2>
 <div class="photo"><img src="assets/photo.jpg?v=$stamp" alt="$photo_alt"></div>
 <div class="cap">$photo_cap</div>

 <div class="foot"><span>Updated $updated</span><span>Rebuilt every 3 hours &middot; GitHub Actions</span></div>
</body>
</html>
""")

def greeting(hour):
    if 5 <= hour < 12: return "Good morning"
    if 12 <= hour < 17: return "Good afternoon"
    return "Good evening"

def main():
    data = {"generated": NOW.isoformat()}
    try: data["weather"] = fetch_weather()
    except Exception as e: sys.stderr.write("weather failed: %s\n" % e); data["weather"] = None
    data["stocks"] = fetch_stocks()
    try: data["launch"] = fetch_launch()
    except Exception as e: sys.stderr.write("launch failed: %s\n" % e); data["launch"] = None
    data["news"] = fetch_news()
    data["photo"] = fetch_photo()
    if data["photo"] is None:
        # Download failed, so the previous photo.jpg is still on the page: keep its caption too.
        try:
            with open(os.path.join(HERE, "data.json"), encoding="utf-8") as f:
                old = json.load(f).get("photo")
            if old and os.path.exists(os.path.join(HERE, "assets", "photo.jpg")):
                data["photo"] = old
        except Exception:
            pass

    with open(os.path.join(HERE, "data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    w = data["weather"] or {"temp": "—", "feels": "—", "cond": "—",
                            "today_hi": "—", "today_lo": "—", "days": []}
    lau = data["launch"] or {"name": "No upcoming launch found", "pad": "", "when": "—", "countdown": ""}
    ph = data["photo"]
    if ph:
        cap = "<b>%s</b> &mdash; &ldquo;%s,&rdquo; %s. %s." % (esc(ph["photographer"]), esc(ph["title"]), esc(ph["year"]), esc(ph["credit"]))
        alt = "%s, %s" % (esc(ph["photographer"]), esc(ph["title"]))
    else:
        cap, alt = "Photograph unavailable today.", "photograph"

    forecast = r_forecast(w["days"]) or "<div><div class='fw'>Forecast unavailable</div></div>"
    out = TEMPLATE.substitute(
        greet=greeting(NOW.hour), bigdate=NOW.strftime("%A %-d %b"), loc=esc(LOC["name"]),
        temp=w["temp"], cond=esc(w["cond"]), feels=w["feels"], hi=w["today_hi"], lo=w["today_lo"],
        forecast=forecast, markets=r_markets(data["stocks"]),
        launch_name=esc(lau["name"]),
        launch_pad=esc((lau.get("pad") or "") + ((" · " + lau["status"]) if lau.get("status") else "")),
        launch_when=esc(lau["when"]), launch_cd=esc(lau.get("countdown", "")),
        headlines=r_headlines(data["news"]),
        photo_cap=cap, photo_alt=alt, stamp=NOW.strftime("%Y%m%d%H%M"),
        updated=NOW.strftime("%-I:%M %p %Z"),
    )
    with open(os.path.join(HERE, "index.html"), "w", encoding="utf-8") as f:
        f.write(out)
    print("Built index.html and data.json at", NOW.isoformat())

if __name__ == "__main__":
    main()
