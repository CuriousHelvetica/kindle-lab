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

ATOM = "{http://www.w3.org/2005/Atom}"
TEASER_MAX = 450  # characters — a teaser, not the article

def _clean_text(s):
    import re
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.sub(r"\s+", " ", html.unescape(s)).strip()
    s = re.sub(r"\s*The post .{0,300}? appeared first on .{0,80}?\.?\s*$", "", s)   # WordPress footer
    s = re.sub(r"\s*(\[(…|\.\.\.)\]|Read More|[Mm]ore\s*(…|\.\.\.)|Continue reading.*)\s*$", "", s)
    return s.strip()

def _teaser(s):
    """First 1-3 sentences, at most TEASER_MAX chars (some feeds put the whole article here)."""
    import re
    s = _clean_text(s)
    if len(s) <= TEASER_MAX:
        return s
    out = ""
    for sent in re.split(r"(?<=[.!?])\s+", s):
        if len(out) + len(sent) + 1 > TEASER_MAX or out.count(". ") >= 2:
            break
        out = (out + " " + sent).strip()
    return out or s[:TEASER_MAX].rsplit(" ", 1)[0] + "…"

def _item_date(it):
    from email.utils import parsedate_to_datetime
    raw = it.findtext("pubDate") or it.findtext(ATOM + "updated") or it.findtext(ATOM + "published")
    try:
        d = parsedate_to_datetime(raw) if it.findtext("pubDate") else datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def _age(d):
    if not d: return ""
    h = int((datetime.now(timezone.utc) - d).total_seconds() // 3600)
    return "just now" if h < 1 else ("%dh ago" % h if h < 48 else "%dd ago" % (h // 24))

def _read_feed(f):
    root = ET.fromstring(_get(f["url"], timeout=25))
    items = root.findall(".//item") or root.findall(".//" + ATOM + "entry")
    out = []
    for it in items[:15]:
        link = it.findtext("link")
        if not link and it.find(ATOM + "link") is not None:
            link = it.find(ATOM + "link").get("href")
        title = _clean_text(it.findtext("title") or it.findtext(ATOM + "title"))
        desc = it.findtext("description") or it.findtext(ATOM + "summary") or it.findtext(ATOM + "content") or ""
        if title and link:
            out.append({"title": title, "teaser": _teaser(desc), "link": link.strip(),
                        "source": f["name"], "date": _item_date(it)})
    return out

def _google_news(t, n):
    """Fallback: headline only (Google's feed has no teaser or direct link)."""
    u = "https://news.google.com/rss/search?q=%s&hl=en-AU&gl=AU&ceid=AU:en" % urllib.parse.quote(t["query"])
    root = ET.fromstring(_get(u, timeout=25))
    out = []
    for it in root.findall(".//item")[:n]:
        title = (it.findtext("title") or "").strip()
        out.append({"title": title.rsplit(" - ", 1)[0] if " - " in title else title,
                    "teaser": "", "link": None, "source": it.findtext("source") or "", "age": ""})
    return out

def fetch_news():
    """Per topic: newest matching story across that topic's outlet feeds, with the outlet's
    own teaser and a direct link. Falls back to a Google News headline if every feed fails."""
    import re
    out, n, used = [], CFG.get("headlines_per_topic", 1), set()
    for t in CFG["news"]:
        cands = []
        for f in t.get("feeds", []):
            try:
                cands += _read_feed(f)
            except Exception as e:
                sys.stderr.write("news feed %s failed: %s\n" % (f["name"], e))
        if t.get("match"):
            rx = re.compile(t["match"], re.I)
            cands = [c for c in cands if rx.search(c["title"] + " " + c["teaser"])]
        cands = [c for c in cands if c["link"] not in used]
        cands.sort(key=lambda c: c["date"] or datetime(1970, 1, 1, tzinfo=timezone.utc), reverse=True)
        picked = []
        for c in cands[:n]:
            used.add(c["link"])
            picked.append({"title": c["title"], "teaser": c["teaser"], "link": c["link"],
                           "source": c["source"], "age": _age(c["date"])})
        if not picked:
            try:
                picked = _google_news(t, n)
            except Exception as e:
                sys.stderr.write("news %s fallback failed: %s\n" % (t["tag"], e))
        out.append({"tag": t["tag"], "items": picked})
    return out

PHOTO_DIR = os.path.join(HERE, "assets", "photos")

def photo_file(p):
    """Stable file name for a photos.json entry, e.g. 'ansel-adams--the-tetons-and-the-snake-river.jpg'."""
    import re, unicodedata
    def slug(t):
        t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
        return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:60].strip("-")
    return slug(p["photographer"]) + "--" + slug(p["title"]) + ".jpg"

def process_photo(p):
    """Download one photo from its source, convert for e-ink, store it in assets/photos/."""
    raw = _get(p["url"], timeout=45)
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("L")  # grayscale (treatment A)
    # Panel-native 1272 px wide (2x of 636 CSS px), but cap the height at 1400 px
    # (~700 CSS px, one screen) so tall portraits don't fill two screens.
    w = 1272; h = round(w * im.height / im.width)
    if h > 1400:
        h = 1400; w = round(h * im.width / im.height)
    im = ImageOps.autocontrast(im.resize((w, h), Image.LANCZOS), cutoff=1)
    os.makedirs(PHOTO_DIR, exist_ok=True)
    im.save(os.path.join(PHOTO_DIR, photo_file(p)), quality=88)

def load_photos():
    with open(os.path.join(HERE, "photos.json"), encoding="utf-8") as f:
        return json.load(f)

def fetch_photo():
    """Pick today's photo. All photos are pre-processed and stored in assets/photos/;
    one that isn't (newly added to photos.json) is downloaded once and stored."""
    photos = load_photos()
    start = NOW.toordinal() % len(photos)
    order = list(range(start, len(photos))) + list(range(0, start))
    for i in order:
        p = photos[i]
        try:
            if not os.path.exists(os.path.join(PHOTO_DIR, photo_file(p))):
                process_photo(p)
            return {"photographer": p["photographer"], "title": p["title"],
                    "year": p.get("year", ""), "credit": p.get("credit", ""), "file": photo_file(p)}
        except Exception as e:
            sys.stderr.write("photo '%s' failed: %s\n" % (p.get("title"), e))
    return None

def cache_all_photos():
    """One-off / maintenance: download and process every photo not yet stored."""
    import time
    photos = load_photos(); ok = 0
    for p in photos:
        if os.path.exists(os.path.join(PHOTO_DIR, photo_file(p))):
            ok += 1; continue
        for attempt in range(3):
            try:
                time.sleep(3)  # be polite to Wikimedia (it rate-limits)
                process_photo(p); ok += 1
                print("stored", photo_file(p)); break
            except Exception as e:
                sys.stderr.write("photo '%s' attempt %d failed: %s\n" % (p["title"], attempt + 1, e))
                time.sleep(20)
    print("%d of %d photos stored in assets/photos/" % (ok, len(photos)))

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
        for h in (t["items"] or [{"title": "— no headline —", "teaser": "", "link": None, "source": "", "age": ""}]):
            meta = " &middot; ".join(esc(x) for x in (h.get("source"), h.get("age")) if x)
            body = ""
            if h.get("teaser"):
                body += "<p>%s</p>" % esc(h["teaser"])
            if h.get("link"):
                body += '<a href="%s">Read the full story at %s &rsaquo;</a>' % (esc(h["link"]), esc(h.get("source") or "source"))
            parts.append('<div class="hd%s"><div class="tag">%s</div><div class="ttl">%s</div>%s%s</div>' % (
                " x" if body else "", esc(t["tag"]), esc(h["title"]),
                ('<div class="src">%s</div>' % meta) if meta else "",
                ('<div class="tz">%s</div>' % body) if body else ""))
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
 .upd{font-size:13px;margin-top:4px;}
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
 h2 .hint{display:none;letter-spacing:1px;font-weight:400;}
 .js h2 .hint{display:inline;}
 .hd .tag{font-size:11px;letter-spacing:2px;text-transform:uppercase;}
 .hd .ttl{font-size:17px;font-weight:600;line-height:1.3;}
 .hd .src{font-size:12px;margin-top:2px;}
 .hd .tz{font-family:Georgia,serif;font-size:16px;line-height:1.45;margin-top:6px;}
 .hd .tz p{margin:0 0 8px;}
 .hd .tz a{color:#000;font-family:Helvetica,Arial,sans-serif;font-size:14px;font-weight:700;}
 /* tap-to-expand: only when JavaScript runs; without JS the teasers simply show */
 .js .hd.x{cursor:pointer;}
 .js .hd.x .tz{display:none;}
 .js .hd.x.open .tz{display:block;}
 .js .hd.x .ttl::after{content:"  \25BC";font-size:11px;}
 .js .hd.x.open .ttl::after{content:"  \25B2";}
 .photo img{display:block;margin:0 auto;max-width:100%;height:auto;border:1px solid #000;}
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
   <div class="upd">Last updated $updated</div>
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

 <h2>Headlines<span class="hint"> &middot; tap to expand</span></h2>
 $headlines

 <h2>Photograph of the day</h2>
 <div class="photo">$photo_html</div>
 <div class="cap">$photo_cap</div>

 <div class="foot"><span>Updated $updated</span><span>Rebuilt daily &middot; GitHub Actions</span></div>
<script>
 (function(){
  document.body.className += " js";
  var hs = document.querySelectorAll(".hd.x");
  for (var i = 0; i < hs.length; i++) {
   hs[i].addEventListener("click", function(e){
    if (e.target && e.target.tagName === "A") return;   // let the link open the article
    this.className = /\bopen\b/.test(this.className) ? this.className.replace(/\s*\bopen\b/, "") : this.className + " open";
   });
  }
 })();
</script>
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

    with open(os.path.join(HERE, "data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    w = data["weather"] or {"temp": "—", "feels": "—", "cond": "—",
                            "today_hi": "—", "today_lo": "—", "days": []}
    lau = data["launch"] or {"name": "No upcoming launch found", "pad": "", "when": "—", "countdown": ""}
    ph = data["photo"]
    if ph and os.path.exists(os.path.join(PHOTO_DIR, ph["file"])):
        cap = "<b>%s</b> &mdash; &ldquo;%s,&rdquo; %s. %s." % (esc(ph["photographer"]), esc(ph["title"]), esc(ph["year"]), esc(ph["credit"]))
        alt = "%s, %s" % (esc(ph["photographer"]), esc(ph["title"]))
    else:
        ph, cap, alt = None, "Photograph unavailable today.", "photograph"
    # Display at half the pixel size (the image is 2x for the Kindle's devicePixelRatio).
    try:
        with Image.open(os.path.join(PHOTO_DIR, ph["file"])) as pim:
            img_size = 'width="%d" height="%d"' % (pim.width // 2, pim.height // 2)
        photo_html = '<img src="assets/photos/%s" %s alt="%s">' % (esc(ph["file"]), img_size, alt)
    except Exception:
        photo_html = ""

    forecast = r_forecast(w["days"]) or "<div><div class='fw'>Forecast unavailable</div></div>"
    out = TEMPLATE.substitute(
        greet=greeting(NOW.hour), bigdate=NOW.strftime("%A %-d %b"), loc=esc(LOC["name"]),
        temp=w["temp"], cond=esc(w["cond"]), feels=w["feels"], hi=w["today_hi"], lo=w["today_lo"],
        forecast=forecast, markets=r_markets(data["stocks"]),
        launch_name=esc(lau["name"]),
        launch_pad=esc((lau.get("pad") or "") + ((" · " + lau["status"]) if lau.get("status") else "")),
        launch_when=esc(lau["when"]), launch_cd=esc(lau.get("countdown", "")),
        headlines=r_headlines(data["news"]),
        photo_cap=cap, photo_html=photo_html,
        updated=NOW.strftime("%a %-d %b, %-I:%M %p %Z"),
    )
    with open(os.path.join(HERE, "index.html"), "w", encoding="utf-8") as f:
        f.write(out)
    legacy = os.path.join(HERE, "assets", "photo.jpg")  # pre-2026-11-10 single-photo file, no longer used
    if os.path.exists(legacy):
        os.remove(legacy)
    print("Built index.html and data.json at", NOW.isoformat())

if __name__ == "__main__":
    if "--cache-photos" in sys.argv:
        cache_all_photos()
    else:
        main()
