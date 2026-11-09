# Kindle Lab

Fun, useful web pages for a **Kindle Paperwhite 12th gen** (firmware 5.20.1.0.2), opened in the device's Experimental Browser over Wi-Fi. No jailbreak required for this route. The Kindle is still used as a normal Kindle — nothing here should risk it.

Account: GitHub `CuriousHelvetica`. Owner uses the Kindle in bed, indoors, on Wi-Fi, for personal use.

## Status

- **Phase 0 — browser capability test: DONE** (tested on-device 2026-11-09 via `kindle-test.html` + `net-test.html`). Verdict below. The big surprise: the browser engine is **modern**, not the ancient WebKit its user agent claims.
- **Phase 1 — morning dashboard: LIVE (2026-11-09).** A pre-rendered static page from live data (weather, AAPL/TSLA/SPCX, next SpaceX launch, headlines, daily B&W photo). Deployed to GitHub Pages at **https://curioushelvetica.github.io/kindle-lab/index.html** (the Kindle bookmark); the scheduled Action rebuilds it every 3 hours. See _The dashboard_ below.

## Confirmed device capabilities (PW 12th gen, fw 5.20.1.0.2, Experimental Browser)

- **Engine is modern — do NOT trust the user agent.** UA reports `AppleWebKit/531.2 ... Version/5.0 Safari ... Kindle/3.0` (a 2009 Safari-4 string), but every modern feature works: `let`/`const`, arrow functions, template literals, classes, `async`/`await`, `Promise`, `fetch`, `querySelector`, `addEventListener`, `canvas` 2D. The UA is a legacy/spoofed label; **feature-detect, never UA-sniff.** We can write modern JS.
- **Viewport:** 636×740 CSS px usable (screen 636×848), `devicePixelRatio` 2 → 1272 physical px wide. Design at **636 CSS px**; render raster/canvas at 2× for crispness.
- **Clock:** device is on **UTC** (timezone offset 0). Convert times explicitly for display.
- **Input:** a tap fires a **`click`** event (not `touchstart`). Bind `click`.
- **Fonts:** Japanese kana + kanji render; `<ruby>` **furigana works** → flashcards fully viable.
- **Graphics:** CSS colors, `canvas` 2D, inline SVG, and PNG data URIs all render. **But gradients band heavily** — the e-ink panel quantizes to ~16 grays (~10 reliably distinguishable). Favor high-contrast; avoid subtle tonal gradients in UI. B&W photos work but will be dithered.
- **CSS:** flexbox YES, grid YES, `position:sticky` YES. (`border-radius`/`box-shadow` reported NO, but that was a test bug — `CSS.supports` needs hyphenated property names; both are almost certainly fine. Re-verify.)
- **Storage:** `localStorage` works and **persists across reloads, navigation, and leaving/reopening the page** (confirmed on-device). Safe for flashcard progress, cached data, and settings.
- **Network:** same-origin `fetch` + `XHR` PASS; external HTTPS `<img>` PASS; **external CORS `fetch` (api.github.com) PASS.** The device does modern TLS and cross-origin fetches fine. Earlier failures were endpoint-specific (worldtimeapi.org; a WebSocket echo host). **WebSocket: FAILS/blocked — do not use.**

## Validated architecture

Public GitHub Pages repo hosts a static page. A **scheduled GitHub Action pre-bakes data** (weather, stocks, headlines, photo-of-the-day) into JSON/HTML committed next to the page; the Kindle just opens a bookmark and same-origin-fetches it. The Mac need not stay on. Keep private data (calendar) off the public page, or serve those parts from the Mac Mini. Direct third-party fetch from the Kindle is possible for CORS-friendly public APIs, but pre-baking is more robust and keeps any API keys server-side (in Action secrets, never on the page).

The dashboard goes one step further than JSON: `build.py` renders a **fully pre-rendered `index.html`** with the data already baked in, so the Kindle loads plain HTML with no client-side fetching — the most robust option for the device.

## The dashboard (build & deploy)

**Files:** `config.json` (your knobs) · `photos.json` (curated public-domain B&W rotation) · `build.py` (fetches everything, processes the photo, renders the page) · `index.html` + `data.json` + `assets/photo.jpg` (generated — do not hand-edit) · `.github/workflows/update.yml` (the scheduled job). `mockup.html`, `kindle-test.html`, `net-test.html`, `photo-test.html` are dev/reference pages.

**Data sources (all keyless):** weather = Open-Meteo · stocks = Yahoo Finance chart API · next launch = The Space Devs Launch Library 2 · headlines = Google News RSS per topic · photo = daily rotation from `photos.json`, converted to grayscale (treatment **A**, chosen on-device) at the panel's native 1272 px.

**Run locally:**

    cd kindle-lab
    pip install pillow
    python build.py        # add LL_BASE=https://lldev.thespacedevs.com to dodge launch rate limits while testing
    python3 -m http.server 8000 --bind 0.0.0.0   # open http://<mac-ip>:8000/index.html on the Kindle

**Customize:** edit `config.json` — add a ticker to `tickers`, change the city `latitude`/`longitude`/`timezone`, or adjust `news` topics and `headlines_per_topic`. Add more photos to `photos.json`. Rebuild to apply.

**Deploy (when ready):** push this folder to a public `kindle-lab` repo → enable GitHub Pages (Deploy from branch: `main` / root) → the Action rebuilds and commits every 3 hours. Bookmark `https://<user>.github.io/kindle-lab/index.html` on the Kindle. No secrets required.

## Serve it to the Kindle

The page is one file with no dependencies, so any of these work:

- **Local server (fastest, Mac must be on):** from this folder run
  ```
  python3 -m http.server 8000 --bind 0.0.0.0
  ```
  then on the Kindle open `http://<mac-lan-ip>:8000/kindle-test.html` (Kindle and Mac on the same Wi-Fi).
- **GitHub Pages (Mac can be off):** push this folder to a public repo (e.g. `kindle-lab`), enable Pages, open the Pages URL. Planned for the recurring/daily features.

## What the test page checks

Device/browser (user agent, screen size, timezone), JavaScript feature support (ES5 vs ES6+, Promise, fetch, localStorage, canvas, WebSocket), localStorage persistence (open counter — survives reload? survives Home + reopen?), tap/touch events, Japanese rendering (kana, kanji, furigana), grayscale rendering (CSS swatches, embedded PNG, canvas, SVG), CSS features, and optional network (XHR + WebSocket) behind buttons.

The page builds a plain-text **Summary** block at the top to read back, plus by-eye questions (Japanese tofu? swatch count? image smoothness?).

## Roadmap (brainstormed features)

1. Morning dashboard — weather, calendar, stock watchlist, next SpaceX launch, Tesla/SpaceX/AI headlines, B&W photo of the day
2. Daily crossword (small, themed)
3. Chess — daily puzzle and/or play the computer (strong engine could run on the Mac Mini)
4. Japanese flashcards with spaced repetition

Interests: photography (esp. B&W), investments, AI/robotics, Tesla, SpaceX, chess.

## Decisions & constraints

- **Firmware:** avoid further Kindle firmware updates to keep the "Vera" jailbreak (reported PW12 support on 5.17.1–5.19.6; 5.20.1 unconfirmed) open as a later option.
- **Browser caveats to verify on-device:** old WebKit; play safe with ES5-style JS; WebSockets reported not to work; heavy pages slow; localStorage reportedly works; browser session reportedly ends when Home is pressed. The test page exists to confirm/deny these.
- **Hosting/privacy:** GitHub Pages on a private repo likely needs a paid plan, so a public site is the default — keep private data (calendar) off a public page, or serve those parts from the Mac Mini instead.

## Open questions (for the feature phase, not the capability test)

- Dashboard: weather city; calendar service (and whether OK on a public page); tickers (reuse `my-stock-watch`?); own photos vs public-domain B&W
- Crossword: English / Japanese / mixed; target solve time
- Chess: player level; puzzles, games, or both
- Japanese: level (kana / N5 / N4 …); vocab / kanji / phrases; furigana or not
- Repo name: **decided — `kindle-lab`** (one umbrella repo; dashboard is a page, flashcards/chess/etc. join later)
