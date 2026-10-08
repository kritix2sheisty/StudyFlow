<p align="center">
  <img src="assets/logo.png" alt="StudyFlow logo" width="96">
</p>

<h1 align="center">StudyFlow</h1>
<p align="center"><strong>Plan smarter. Study better.</strong></p>

StudyFlow is a student-focused scheduling application that helps students organize their academic workload and decide what to study next. Students add their assignments and the times they are free to study, and StudyFlow builds a week of study sessions that lands every piece of work before its due date, flagging anything at risk.

## Use StudyFlow

**Website:** [studyflow-production-d5e4.up.railway.app](https://studyflow-production-d5e4.up.railway.app)

Open it in any browser on a computer or phone. There is nothing to install. Scan the code to open it on your phone:

<p align="center">
  <a href="https://studyflow-production-d5e4.up.railway.app">
    <img src="assets/share-qr.svg" alt="QR code for the StudyFlow website" width="200">
  </a>
</p>

### Getting started

1. **Create an account** with your email and a password (8 characters or more). The browser keeps you signed in until you log out, and the same account works on the phone app.
2. **Add your assignments**: name, subject, due date, estimated hours and priority.
3. **Add when you can study**: recurring weekly blocks such as Monday 4–6 PM. StudyFlow never invents free time.
4. **Generate your study plan.** StudyFlow places the work into your study time, before each due date, and tells you if anything will not fit.

### What's in the app

| Page | What it does |
| --- | --- |
| Dashboard | Today's overview: assignment count, hours required and scheduled, upcoming work by urgency, your study times and today's plan |
| Assignments | Add, edit, complete and delete assignments |
| Schedule | The generated week, day by day, with each assignment's scheduling status |
| Progress | Overall completion, per-assignment progress, deadline risk and finished work |
| Focus | One study session at a time with a countdown timer and breaks |

The **Share** button in the header opens the QR code and a copy-link button so classmates can open StudyFlow too.

## Current Progress

### Phase 1 — Academic Data Management

* Add, view, edit, and delete classes
* Add, view, edit, and delete assignments
* Add, view, and delete tests
* Add and delete available study-time slots
* View assignments due within the next 7 days
* Mark assignments as complete/incomplete
* Store and manage academic data

### Phase 2 — Assignment Prioritization

* Exclude completed assignments
* Identify overdue and due-today assignments
* Calculate assignment urgency
* Consider assignment priority
* Consider estimated workload (capped, so size never outranks a deadline)
* Rank assignments using a weighted scoring system
* Automated test suite: 13 scenarios plus every prioritization promise (`tests/test_scheduler.py`)

#### How prioritization decides

StudyFlow's rule of thumb: **deadlines first, importance second, size is a nudge, never a veto.**

Missing a deadline is the one outcome a scheduler must never cause, and the
schedule builder works through the prioritized list in order anyway. So a
small task due tomorrow goes ahead of a big task due next week: the big task
loses an hour or two of lead time, whereas the other order could cost the
small task its deadline.

The score is a weighted blend, not an exact optimum:

```
score = urgency × 5  +  priority × 3  +  min(hours, 5) × 0.5
```

where urgency is `10 / days_left`. Overdue and due-today items are a separate
tier that always sorts first. The weights and the 5-hour effort cap are chosen
so that these promises hold, and each one has a test:

1. Completed assignments are never listed.
2. Overdue or due-today work comes before everything else. Among those,
   priority decides, then size. How late something is does not matter.
3. Anything due tomorrow comes before anything due later, whatever its
   priority or size.
4. On the same due date, higher priority wins no matter the size.
5. On the same due date and priority, the bigger task goes first, because it
   needs to be started sooner.
6. From two days out, importance and size can pull a task ahead of one due a
   day or two sooner. A 10-hour high-priority exam prep due in four days
   starts before a 1-hour low-priority worksheet due in three.
7. Up to five days out, a deadline still beats anything due much later. From
   six days out, deadline pressure has faded and importance and size decide,
   so a big high-priority project due next term outranks a small low-priority
   worksheet due in a month.

The full rationale, including the alternatives that were rejected, is in the
module docstring of `scheduler.py`.

### Phase 3 — Schedule Generation (in progress)

* Turn recurring weekly study slots into concrete, dated study blocks
* Place work on or before its due date, never after
* Fill by earliest deadline first, with the Phase 2 ranking breaking ties
* Split large assignments across several blocks and days
* Insert breaks between study periods
* Report any work that could not fit before its due date
* Test suite for deadlines, allocation and break behaviour (`tests/test_schedule_builder.py`)
* Schedule quality: scheduled, unscheduled and required hours, and a completion percentage (`schedule_analyzer.py`)
* Assignment-level analysis: hours scheduled, hours remaining and a COMPLETE / PARTIAL / UNSCHEDULED status per assignment
* Analysis report: `format_analysis()` prints the totals and, per assignment, status, hours and deadline risk (CLI: View schedule analysis)
* At-risk detection: assignments that are not completed and not fully scheduled
* One workflow: `generate_study_plan()` prioritizes, schedules, analyzes and flags in one call, and `format_study_plan()` renders the weekly report (`study_plan.py`; CLI: Generate study plan)

### Phase 3 milestone — End-to-end workflow

* `python main.py` opens a grouped menu: manage classes, assignments, tests and study time, then
  **Generate study plan** runs the whole pipeline and prints the weekly report
* Scripted end-to-end test drives the menus like a student would (`tests/test_main.py`)

### Phase 4 — Intelligent Scheduling (in progress)

* Time-remaining awareness: `available_hours_before_deadline()` measures the study time between today and an assignment's due date (`schedule_optimizer.py`)
* Deadline risk ratio: `deadline_risk_ratio()` divides that available time by the hours an assignment still needs (0.5 means half the time needed; infinity means nothing left to do)
* Risk level: `risk_level()` turns the ratio into CRITICAL (under 1), HIGH (1 to 1.5), MODERATE (1.5 to 2) or LOW (2 and above)

### Phase 5 — Web app, accounts and hosting

* Reflex website with Dashboard, Assignments, Schedule, Progress and Focus pages
* Student accounts: each student's assignments, study time and plan are private; sign-in persists in the browser
* HTTP API (`api/`) shared by the website and the phone app
* Expo phone app (`mobile/`) that can generate and refresh the plan
* Hosted on Railway: the API (with its SQLite database on a volume) and the public website run as two services
* Branded design: StudyFlow logo, QR share dialog, light and dark themes

### Future Development

* Improve schedule optimization (spread work evenly, cap hours per day)
* iPhone build of the mobile app (needs the Apple Developer Program)
* Introduce AI-assisted study recommendations

## Scheduling Algorithm

StudyFlow currently uses a **greedy, deadline-aware** scheduling approach.

1. Remove completed assignments.
2. Prioritize the remaining assignments using the Phase 2 scoring system.
3. Generate concrete study blocks from the student's recurring time slots.
4. Re-order the assignments by due date, earliest first, using the Phase 2
   ranking to break ties.
5. Assign each assignment's work to the earliest available blocks on or
   before its due date, splitting it across blocks when necessary.
6. Insert a break between study periods that share a block.
7. Record any work that could not be scheduled before its due date.

Greedy means each placement is decided once and never revisited. This approach
was chosen because it is simple, predictable, and computationally efficient.
It does not guarantee the mathematically optimal schedule.

**Why earliest deadline first?** The Phase 2 ranking answers "what should I
work on next?" and blends urgency, importance and size. Placing hours in that
order can let a large, important task due later swallow the time a small task
due sooner needed. Ordering placement by deadline instead is a classical
result: when work can be split, it meets every deadline whenever any order
can. Phase 2 still decides among assignments that share a due date.

**Known limitations.** Work is front-loaded into the earliest blocks rather
than spread evenly across the days before a deadline. Breaks can leave a few
minutes unused. There is no cap on hours per day and no preference for
variety. Future versions may explore more advanced scheduling and
optimization techniques once StudyFlow defines what "better" means.

## Running the website locally

```
pip install -r requirements.txt
reflex run
```

Then open http://localhost:3000. Without a `.env`, the website keeps its own SQLite database in `data/` and serves the API itself. With a `.env` that sets `STUDYFLOW_API_URL` and `STUDYFLOW_WEB_KEY` (see *Hosting the website* below), your laptop uses the hosted API and the same accounts as the public site.

The original command-line version is still available with `python main.py`.

## Design

The look follows the logo sheet:

| | |
| --- | --- |
| Indigo (primary) | `#2B2F9D` |
| Navy (text, dark mode background) | `#15193F` |
| Orange (accent) | `#F5A83C` |
| Paper (light background) | `#F6F7FB` |
| Headings | [Fraunces](https://fonts.google.com/specimen/Fraunces) |
| Body text | [Inter](https://fonts.google.com/specimen/Inter) |

`assets/studyflow.css` holds the theme. It redefines the Radix indigo and slate colour scales, so every button, badge and card picks up the brand colours in both light and dark mode. `assets/logo.png` is the app icon and `assets/share-qr.svg` is the QR code for the public website. If the website moves, regenerate the QR code (for example with the `segno` package) and set `STUDYFLOW_PUBLIC_URL` so the Share dialog shows the new link.

## Running the tests

```
pip install pytest
pytest
```

Tests live in `tests/`. A `conftest.py` at the project root puts the project
on the import path, so `pytest` works from the project root without any
packaging.

## Mobile client (Expo)

`mobile/` is a React Native app built with Expo that talks to the same API
as the web app. Students run it on their own phone through the Expo Go app
or a shared Android build. Point `EXPO_PUBLIC_API_URL` at the hosted API
so the phone works off campus. For laptop testing, use the LAN address
and the same Wi-Fi as the computer running StudyFlow.

1. Start StudyFlow as usual (`reflex run`); the API listens on the backend
   port on every interface.
2. Find the laptop's LAN address (`ipconfig`, the IPv4 line).
3. Set it up once:

   ```
   cd mobile
   npm install
   copy .env.example .env      # then edit EXPO_PUBLIC_API_URL to https://<your-api-host>
                               # (or http://<LAN IP>:<backend port> for laptop testing)
   ```

4. Run it: `npx expo start`, then scan the QR code with Expo Go (Android)
   or the camera app (iPhone). The sign-in screen shows the server address
   it is using at the bottom.
5. Tests: `npm test`. Type check: `npm run typecheck`. Health: `npm run doctor`.

Notes:

* `EXPO_PUBLIC_API_URL` is baked in at bundle time; after editing `.env`
  restart with `npx expo start -c`.
* Windows asks once whether Node may accept connections; allow it on private
  networks. The Wi-Fi profile on the laptop must be *Private*, and Python
  (the API) needs the same permission.
* On Wi-Fi that isolates devices (many school and guest networks), phones
  cannot reach the laptop at all. Turn on the laptop's Mobile hotspot,
  join it from the phone, and use the hotspot address (usually
  `192.168.137.1`) in `.env`. `npx expo start --tunnel` only tunnels the app
  bundle, not the API.
* An Android emulator reaches the laptop at `10.0.2.2`, not the LAN IP.
* Expo Go allows plain `http://` to the laptop. A standalone build later will
  need cleartext traffic enabled on Android and an App Transport Security
  exception on iOS.

## Hosting the API (so phones work without the laptop)

The phone app only needs the API, and the API runs without Reflex:

```
STUDYFLOW_DB_PATH=/data/studyflow.db uvicorn api_server:app --host 0.0.0.0 --port 8010
```

`api_server.py` exposes the same routes the web app mounts, creates the
tables on start, and keeps the database wherever `STUDYFLOW_DB_PATH`
points (default: `data/studyflow.db`). `requirements-api.txt` is the
API-only dependency list, and the `Dockerfile` packages exactly that for a
container host: it expects a volume at `/data` and reads `PORT`.

Steps on a container host with a persistent volume (Railway's free plan,
for example):

1. Create the project from this GitHub repository; the host detects the
   `Dockerfile`.
2. Add a volume mounted at `/data`.
3. Set `STUDYFLOW_DB_PATH=/data/studyflow.db` (already the image default)
   and let the host set `PORT`.
4. Set `TZ` to the students' timezone (the image defaults to
   `America/La_Paz`). Hosts run in UTC, and every "today" in StudyFlow
   comes from the server clock, so without it a plan made on Monday
   evening is already Tuesday's.
5. Open `https://<your-app-host>/api/health`; it answers `{"status":"ok"}`.
6. Put that address in the phone app's build (below). Keep a copy of the
   database now and then: it is one small file at `/data/studyflow.db`.

Hosts without a persistent disk (Render's free tier, for example) lose the
SQLite file on every restart; they need a streaming backup such as
Litestream to an object store, which is not set up here.

The image sets `STUDYFLOW_TRUST_PROXY=1` so login limits follow each
phone's address (`X-Forwarded-For`) rather than the host's reverse
proxy. Leave that unset when you run the API on a laptop.

After the first API deploy, attach a volume at `/data` in the Railway
dashboard (the SQLite file lives there). Then set `EXPO_PUBLIC_API_URL`
in the phone app to `https://<your-api-host>` with no trailing slash,
rebuild or restart Expo with `-c`, and students can generate a plan
from Today without being on your Wi-Fi.

### Hosting the website against the hosted API

The website is a client of the API whenever `STUDYFLOW_API_URL` is set;
it then keeps no data of its own and mounts no API. So it can run on a
host with no disk. Students open the public website URL in a browser;
they do not need your laptop.

`Dockerfile.web` and `Caddyfile` are the Reflex production image
(frontend on `PORT`, backend events on 8000). It is a **second**
Railway service from this same repo. Do not replace the API service's
Dockerfile.

On the **existing API** service, add:

- `STUDYFLOW_WEB_KEY` — the same long random string as on the website

On the **new website** service:

1. New service → GitHub repo `StudyFlow` (same project as the API).
2. Add a **variable** `RAILWAY_DOCKERFILE_PATH=Dockerfile.web`
   (the dashboard Dockerfile field is overwritten by the repo if you
   only set it there). A good deploy log says `caddy` / `reflex run`,
   not `uvicorn running on`.
3. Variables:
   - `STUDYFLOW_API_URL=https://<your-api-host>` (no trailing slash)
   - `STUDYFLOW_WEB_KEY` — identical to the API service
   - `TZ` — the students' timezone (image default `America/La_Paz`)
4. Networking → Generate domain.
5. Health check path: `/_health` (not `/api/health`; this container has no API).
6. Open `https://<your-web-host>/`; sign in with the same account as the phone.

Make a web key with
`python -c "import secrets; print(secrets.token_urlsafe(32))"`.
Keep it out of git (it lives in the gitignored `.env` on the laptop).

Local `reflex run` still uses `.env` (`STUDYFLOW_API_URL` and
`STUDYFLOW_WEB_KEY`) so your laptop matches production.

A sign-in on the website is kept in this browser until the student logs
out. Use the same email on the phone.

### Getting the phone app to students without the laptop

Expo Go can no longer open a published update for anyone but members of
the account that owns the project (since May 2026), so the practical
route is an Android build shared by link, with updates published over
the air afterwards:

```
npm install --global eas-cli
eas login                       # a free Expo account
cd mobile
eas init                        # links the project; adds the projectId to app.json
eas update:configure            # adds updates.url to app.json
eas env:create --name EXPO_PUBLIC_API_URL --value https://<your-app-host> --environment preview --visibility plaintext
eas build -p android --profile preview    # an APK; share the link it prints
eas update --channel preview --environment preview --message "what changed"   # later changes, no reinstall
```

`mobile/eas.json` already defines the `preview` profile (internal
distribution, APK, channel `preview`) and `app.json` pins the runtime to
the Expo SDK. The free plan allows 15 Android builds a month; updates are
unlimited. iPhones need the paid Apple Developer Program for a build; until
then iPhone users can be added as Viewers of an Expo organisation that owns
the project and open it in Expo Go, signed in.

## Technologies

* Python
* SQLite
* Reflex *(website)*
* Starlette *(HTTP API, `api/`)*
* React Native with Expo *(mobile client, in `mobile/`)*
* Docker, Caddy and Railway *(hosting)*
* Algorithms and data structures
* AI/LLM integration *(future phase)*

## Project Goal

The long-term goal of StudyFlow is to create a practical academic scheduling tool that can intelligently prioritize and organize a student's workload while providing understandable recommendations about why certain tasks should be completed first.
