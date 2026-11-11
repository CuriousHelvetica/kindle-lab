# Kindle Lab — Setup & Operations Manual

Everything needed to understand, run, repair and renew the **morning dashboard** without any earlier conversation. `README.md` is the project overview (device findings, roadmap); this file is the detailed "how it is wired up and how to look after it".

Last updated: 2026-11-11.

---

## 1. The whole system at a glance

```
 cron-job.org timer                     GitHub (repo CuriousHelvetica/kindle-lab, public)
 ──────────────────                     ───────────────────────────────────────────────
 daily 16:10 America/New_York  ──POST──▶  Actions workflow "Update dashboard" (update.yml)
 (10 min after the US close)              1. checkout repo
                                          2. python build.py
                                             ├─ fetch weather / stocks / launch / headlines
                                             ├─ pick today's photo from assets/photos/
                                             └─ write index.html + data.json
                                          3. commit + push to main (only if changed)
                                                   │
                                                   ▼
                                          GitHub Pages (Deploy from branch main / root)
                                                   │  ~1 min later
                                                   ▼
                    Kindle bookmark: https://curioushelvetica.github.io/kindle-lab/index.html
```

- The Kindle only ever loads static files from GitHub Pages. It never contacts Wikimedia, Yahoo, etc.
- The Mac does not need to be on.
- No secrets live in the repo. The only secret (the GitHub token) lives in cron-job.org.

**When it updates (Sydney time):** the run is pinned to New York time, so on your clock it moves with US and Sydney daylight saving:

| Period (approx.) | US close (Sydney) | Run (Sydney) |
|---|---|---|
| Early Nov – early Mar | 8:00 AM | **8:10 AM** |
| Early/mid Mar – early Apr | 7:00 AM | 7:10 AM |
| Early Apr – early Oct | 6:00 AM | 6:10 AM |
| Early Oct – early Nov | 7:00 AM | 7:10 AM |

Add a minute or two for the build and for GitHub Pages to republish.

---

## 2. Accounts and services

| What | Where | Owner / notes |
|---|---|---|
| Code + generated page | github.com/CuriousHelvetica/kindle-lab (public) | GitHub account `CuriousHelvetica` |
| Hosting | GitHub Pages, source = branch `main`, folder `/` (root) | Free for public repos |
| Build runner | GitHub Actions, workflow `.github/workflows/update.yml` | Free for public repos |
| Daily trigger | cron-job.org, job title **"kindle-lab timer"** | Free account owned by the user (their own email/password) |
| Trigger credential | GitHub fine-grained personal access token **"kindle-lab timer"** | Created 2026-11-11, **expires 2027-11-10** |
| Weather | Open-Meteo (api.open-meteo.com) | Keyless |
| Stocks | Yahoo Finance chart API (query1.finance.yahoo.com/v8/finance/chart) | Keyless, unofficial |
| Next launch | The Space Devs Launch Library 2 (ll.thespacedevs.com/2.2.0) | Keyless, rate-limited (use `LL_BASE=https://lldev.thespacedevs.com` when testing locally) |
| Headlines | Outlet RSS feeds per topic (Electrek, Teslarati; Space.com, Teslarati SpaceX, SpaceNews, Spaceflight Now; TechCrunch AI, The Robot Report, IEEE Spectrum Robotics). Fallback: Google News RSS (AU) | Keyless |
| Photos | Wikimedia Commons (one-time download; stored in repo) | Public domain |
| Local tools on the Mac | `gh` CLI (installed + authenticated), Python 3 + Pillow | Lets future Claude sessions inspect runs, push, etc. |

---

## 3. GitHub repo and Pages

- Repo: `https://github.com/CuriousHelvetica/kindle-lab`, default branch `main`.
- Pages: Settings → Pages → *Build and deployment* → Source **Deploy from a branch**, Branch **main**, folder **/ (root)**. GitHub runs its own `pages-build-deployment` workflow after every push; that is normal.
- Kindle bookmark: `https://curioushelvetica.github.io/kindle-lab/index.html`.
- `.gitignore` excludes `assets/_src/` and the three Phase-0 photo test variants (`photo_gray.jpg`, `photo_dither16.png`, `photo_bw.png`), so `photo-test.html` only works when served from the Mac, not on Pages. That's intentional.

---

## 4. The build workflow (`.github/workflows/update.yml`)

- **Trigger:** `workflow_dispatch` only (started by the cron-job.org timer, or by hand). There is deliberately **no `schedule:` trigger**; see §10 for why.
- **Steps:** checkout → Python 3.11 → `pip install pillow` → `python build.py` → commit and push if anything changed.
- **Commit step:** `git add -A index.html data.json assets`, commit as `kindle-lab-bot` with message `Update dashboard <UTC time>`, then `git pull --rebase origin main` (in case someone pushed during the build) and `git push`.
- **Permissions:** `contents: write` (needed to push). **Concurrency:** group `update-dashboard`, so two runs never overlap.
- A run takes about 20 seconds. Each run makes one commit, so one per day.

**Run it by hand:** GitHub → repo → **Actions** → *Update dashboard* → **Run workflow** → branch `main` → Run. Or from the Mac: `gh workflow run update.yml --ref main` (in the `kindle-lab` folder).

---

## 5. The daily trigger (cron-job.org) — full setup

### 5.1 Why an outside timer
GitHub's built-in scheduler proved unreliable for this repo (details in §10). GitHub's docs say scheduled runs "can be delayed" and "may be dropped" under load. A dedicated timer service fires on time and simply presses the workflow's "Run" button through GitHub's API.

### 5.2 The GitHub token (step by step)
1. Signed in as `CuriousHelvetica`, open **https://github.com/settings/personal-access-tokens/new** (Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token).
2. **Token name:** `kindle-lab timer`.
3. **Expiration:** Custom, the maximum of about 1 year. The current token **expires 2027-11-10** (GitHub reported `github-authentication-token-expiration: 2027-11-10 13:00:00 UTC`).
4. **Repository access:** *Only select repositories* → `kindle-lab`.
5. **Repository permissions → Actions: Read and write.** Nothing else. ("Metadata: Read-only" is added automatically.) This token can only start/see workflow runs on this one repo; it cannot read or change code, settings or other repos.
6. Generate, copy the token (shown only once), paste it into cron-job.org (below). **Never put it in the repo, a file, or a chat.**
7. To revoke instantly: same settings page → the token → Delete. The timer then stops working.

### 5.3 The cron-job.org job
Account at https://cron-job.org (the user's own; confirm the sign-up email before creating jobs). Job settings:

| Setting | Value |
|---|---|
| Title | `kindle-lab timer` |
| URL | `https://api.github.com/repos/CuriousHelvetica/kindle-lab/actions/workflows/update.yml/dispatches` |
| Schedule | Every day at **16:10** |
| Time zone | **America/New_York** (keeps it 10 min after the US close all year) |
| Request method | `POST` |
| Header | `Accept: application/vnd.github+json` |
| Header | `Authorization: Bearer <token>` (the word Bearer, a space, the token) |
| Header | `X-GitHub-Api-Version: 2022-11-28` |
| Header | `Content-Type: application/json` |
| Request body | `{"ref":"main"}` |
| Notifications | Email on failure: ON |

**Expected reply:** `204 No Content`, which means "accepted, workflow started" (it is a success even though it looks like an error). First test run: 2026-11-11 01:44:52 UTC → returned 204 → GitHub run started the same second and succeeded; the live page updated to "Last updated Wed 11 Nov, 12:45 PM AEDT".

**What error replies mean:**
| Reply | Likely cause | Fix |
|---|---|---|
| 401 Bad credentials | Token expired/deleted, or "Bearer " missing | Make a new token (§5.2), update the Authorization header |
| 403 Resource not accessible | Token lacks Actions: write, or not scoped to kindle-lab | Edit the token's permissions/repos |
| 404 Not Found | URL typo, workflow file renamed, or token can't see the repo | Check the URL; it must end `/workflows/update.yml/dispatches` |
| 422 Unprocessable | Body wrong, or branch `main` doesn't exist | Body must be exactly `{"ref":"main"}` |
| 400 / version error | API version header retired | Update `X-GitHub-Api-Version` (§9) |

---

## 6. What `build.py` does

Config lives in `config.json`: location (St Ives, NSW; lat −33.73, lon 151.16; timezone Australia/Sydney), tickers (AAPL, TSLA, SPCX), news topics (Tesla, SpaceX, "AI robotics"), `headlines_per_topic` (1).

| Section | Source / logic | If the source fails |
|---|---|---|
| Masthead | Greeting by Sydney hour: morning 5–11, afternoon 12–16, evening otherwise. Big date = build date. **"Last updated Wed 11 Nov, 8:10 AM AEDT"** line under the location (also in the footer). | n/a |
| Weather | Open-Meteo current + 3-day daily, °C | Shows "—" and "Forecast unavailable" |
| Markets "at last close" | `regularMarketPrice` vs the **second-to-last daily close** from the 5-day series. (Do NOT use `chartPreviousClose` with `range=5d`; that is the close before the 5-day window and gave 5-day changes. Fixed 2026-11-09.) Name from Yahoo `shortName`. | That row shows "—" / "n/a" |
| Next SpaceX launch | Launch Library 2 `launch/upcoming/?search=SpaceX&limit=1`; time shown in Sydney time, countdown "in ~N hours/days" | "No upcoming launch found" |
| Headlines | Per topic: newest story across that topic's outlet feeds (`config.json` → `news[].feeds`), optionally filtered by the topic's `match` regex. Shows title, outlet and age; **tap to expand** the outlet's own teaser (≤450 chars, max 3 sentences) plus a "Read the full story at <outlet> ›" link. The same article is never used for two topics. See §6.1 | If every feed for a topic fails: Google News headline only (no teaser/link); if that fails too, "— no headline —" |
| Photo | Today's entry from `photos.json`, served from `assets/photos/` (see §7) | Next photo in the list; if none at all, "Photograph unavailable today." |

Output: `index.html` (fully pre-rendered; no client-side fetching; one tiny script for tap-to-expand) and `data.json` (the same data, for debugging or future pages).

### 6.1 Headlines: teasers and tap-to-expand (added 2026-11-11)

- **Why outlet feeds, not Google News:** Google News RSS gives only a headline, the outlet name and a Google redirect link: no story text and no direct article address. Outlet feeds include their own 1–3 sentence teaser and a direct link.
- **Why teasers and not whole articles:** the page and repo are public, so copying full articles would republish copyrighted text. Teasers are what outlets publish in their feeds for syndication, and are capped at 450 characters (IEEE Spectrum puts the whole article in its feed; it gets cut to a teaser). For the whole story, tap the link to open the article on the outlet's site; the Kindle's Back button returns to the dashboard. (An AI-summary option was considered and declined: it needs an API key.)
- **Teaser clean-up** strips HTML and feed boilerplate ("The post … appeared first on …", "Read More", "more…", "[…]").
- **Topic filters (`match`)** keep mixed feeds on topic: Tesla = `Tesla|Cybertruck|Model [3SXY]|Robotaxi|FSD|Optimus|Supercharg`; SpaceX = `SpaceX|Starship|Falcon|Starlink|Dragon|Starbase`; AI & Robotics has none (all its feeds are on topic).
- **Tap behaviour:** headlines start collapsed with a ▼; tapping one shows its teaser and link (▲); tapping again collapses it. Tapping the link opens the article. If JavaScript ever doesn't run, the teasers are simply shown expanded: nothing breaks. "· tap to expand" appears next to the HEADLINES heading only when the script runs.
- **Change outlets:** edit `news[].feeds` in `config.json` (`name` is shown as the source; `url` must be an RSS/Atom feed). Feeds tested 2026-11-11: Electrek, Teslarati, Space.com, SpaceNews, Spaceflight Now, TechCrunch AI, The Robot Report, IEEE Spectrum all OK; NASASpaceflight blocks bots (403); Not a Tesla App and InsideEVs teasers too short; MIT Technology Review teasers start with newsletter boilerplate.
- **Not yet confirmed on the Kindle itself:** tap-to-expand was tested in a desktop browser at Kindle size; the device fires `click` on tap (Phase 0), so it should work.

---

## 7. The photo rotation

- **31 public-domain B&W photos**, listed in `photos.json` (photographer, title, year, credit, source URL).
- **All 31 are pre-processed and stored** in `assets/photos/` (~12 MB total, 190–670 KB each). The daily build downloads nothing. It just points the page at today's file.
- **Processing** (done once per photo): grayscale (treatment "A", chosen on-device), auto-contrast (1% cutoff), resized to 1272 px wide (2× the 636 CSS px screen), **height capped at 1400 px** (~one screen) so tall portraits fit, JPEG quality 88. The page shows it at half its pixel size, centered.
- **File names** come from photographer + title, e.g. `ansel-adams--the-tetons-and-the-snake-river.jpg`. Once stored, the Wikimedia link doesn't matter, so renamed/deleted Wikimedia files can't break the page.
- **Which photo today:** `date.toordinal() % 31` → list position, so **list order = day order**. The list is arranged so no photographer appears on consecutive days and the three Canyon de Chelly shots are spread out (positions 10, 18, 28).
- **Self-healing:** if a listed photo has no stored file, the daily build downloads and stores it once.

**Add a photo:**
1. Find it on Wikimedia Commons; confirm it's public domain.
2. Add an entry to `photos.json`, with URL format `https://commons.wikimedia.org/wiki/Special:FilePath/<File_name>?width=1600`. Mind the position (it sets the day) and avoid putting it next to the same photographer.
3. `python build.py --cache-photos`, then commit `photos.json` + `assets/photos/` and push. (Or just push `photos.json` and let the next daily build fetch it.)

**Remove a photo:** delete its entry from `photos.json` and its file from `assets/photos/`; commit.

**Re-process / lighten a photo:** delete its file, then `python build.py --cache-photos`. To tweak one by hand, edit the stored JPEG directly, keeping the same name and ≤1272×1400 px.

**Known dark ones** to watch on e-ink: Curtis *The Vanishing Race*. Lighten individually if they look muddy.

**Credits:** each caption shows the source (U.S. National Archives, Library of Congress, The Met Open Access, State Library of NSW, or "Public domain, via Wikimedia Commons").

---

## 8. Health checks and troubleshooting

**Did today's update happen?** Look at the line under "St Ives, NSW": *Last updated <today>, ~8:10 AM* (see §1 table for other seasons). The big date should be today.

| Symptom | Check | Fix |
|---|---|---|
| Page shows yesterday | cron-job.org job history (did it fire? reply code?), then GitHub Actions tab (is there a `workflow_dispatch` run today?) | See §5.3 error table; run by hand meanwhile (§4) |
| Run exists but failed | Actions → the run → log | Usually a code/data-source issue; see `build.py` |
| Run succeeded, page old | Pages deploy can lag 1–2 min; the Kindle may cache | Wait, then reload on the Kindle |
| One section shows "—" | That source failed (others are independent) | Usually transient; check next day |
| Photo missing | `assets/photos/<file>` exists? | `python build.py --cache-photos`, commit |

From the Mac (in `kindle-lab/`):
```
gh run list --workflow update.yml -L 5          # recent runs and what triggered them
gh run view <id> --log                          # a run's full log
gh workflow run update.yml --ref main           # start a run now
curl -s https://curioushelvetica.github.io/kindle-lab/index.html | grep -o 'Last updated[^<]*'
```

---

## 9. Maintenance calendar

| When | What |
|---|---|
| **Before 2027-11-10** | **GitHub token expires.** Create a new one with the same settings (§5.2) and paste it into the cron-job.org Authorization header. Then do a cron-job.org *Test run*: expect `204`. GitHub usually emails a reminder a week before. |
| At the same renewal | Update `X-GitHub-Api-Version` to the current version listed at https://docs.github.com/en/rest/about-the-rest-api/api-versions. `2022-11-28` was deprecated 2026-03-10 and **sunsets 2028-03-10**. |
| Occasionally | Check cron-job.org failure emails; glance at Actions for red runs. |
| If Yahoo/LL2/Google change | A section shows "—" for days → the source's API changed; fix in `build.py`. |
| Git history | Grows only via `index.html`/`data.json` (a few KB/day) plus new photos added; ~12 MB of photos already stored. No action needed. |

---

## 10. History and lessons learned (2026-11-09 → 11)

- **2026-11-09** — Dashboard built and deployed; GitHub schedule every 3 h.
- **2026-11-09, code review (Opus 5.5):**
  - **Stock % change was wrong** (showed 5-day change; TSLA showed −10.4% when the daily move was +4.2%). Fixed as in §6.
  - Greeting was always "Good morning"; footer said "daily" while running every 3 h; photo caption was wrong when a download failed; UTF-8 file handling; Action push race (`pull --rebase`); `kindle-test.html` CSS check used camelCase names (`CSS.supports` needs `border-radius`).
- **Schedule changed to once a day**, just after the US close: there's nothing new during Sydney daytime (US market closed), and every run makes a commit.
- **"Last updated" stamp** added under the masthead so a stale page is obvious.
- **Photos:** 2 of the original 4 Wikimedia links had died (404). Expanded to 31 verified masters, then **stored all of them in the repo** so the page no longer depends on Wikimedia daily. Height cap added for tall portraits.
- **GitHub's scheduler did not work for this repo:** first UTC cron (21:15 UTC) → no run on 10 Nov; then `timezone: America/New_York` cron (16:10) → no run at 8:10 AM 11 Nov; the first-ever scheduled run arrived **4 hours late** (01:12 UTC 11 Nov = 12:12 PM Sydney). Note: a run skipped by GitHub is never made up, and pushing a schedule change replaces any pending slot.
- **2026-11-11:** headlines switched from Google News to outlet feeds with tap-to-expand teasers + full-story links (§6.1).
- **Fix (2026-11-11):** cron-job.org → GitHub API `workflow_dispatch` (§5), test-run OK (204), and the `schedule:` trigger removed so the "Last updated" time unambiguously reflects the timer.
- **Lesson:** don't rely on GitHub's `schedule:` for anything time-sensitive; use an external trigger.

---

## 11. Working locally

```
cd "kindle-lab"
pip install pillow
python build.py                    # full build (writes index.html, data.json)
LL_BASE=https://lldev.thespacedevs.com python build.py   # avoid launch API rate limits while testing
python build.py --cache-photos     # download/process any photos not yet in assets/photos/
python3 -m http.server 8000 --bind 0.0.0.0                # then on the Kindle: http://<mac-lan-ip>:8000/index.html
```

A local build overwrites `index.html`/`data.json`. Either commit them (this publishes that build immediately) or discard them (`git checkout -- index.html data.json`) and let the timer publish the next one.
