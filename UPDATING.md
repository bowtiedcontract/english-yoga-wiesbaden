# Updating the schedule

The site is one file, `index.html`. All the data sits in one block at the top of the `<script>`, between
`/* ===== DATA ... */` and `/* ===== END OF DATA ===== */`.

## Automatic weekly update (GitHub Actions)

`.github/workflows/weekly-update.yml` runs **every Sunday at 16:05 UTC** (18:05 Berlin in summer, 17:05 in winter):

1. `scripts/update.py` (Python 3 standard library only) fetches the next two weeks from the public
   Eversports schedule-widget feeds of Studio 85 Hochheim, Studio 85 Biebrich, Balance Yoga Mainz,
   Yogaplus Mainz and Little Big Ganesha. On a Sunday that's Monday through the Sunday after next. Midweek it's today through next Sunday.
2. It keeps only classes whose **title** marks them as English (`ENG`, `English`, `engl.`, `DE/ENG`,
   `bilingual`, case-insensitive) and maps them to the page schema. Little Big Ganesha's titles are
   not marked, so that studio uses a slot list instead (see below). It also adds the fixed PRAXYS template
   (Tue 18:30–19:30, Thu 18:00–19:00, "English not confirmed") and holiday notes for Hesse and
   Rhineland-Palatinate public holidays in the range (hardcoded through 2027 in `HOLIDAYS`).
   Medical appointments are never written, including titles that look like a doctor's appointment,
   physiotherapy, or a Heilpraktiker session.
3. It rewrites **only** `LAST_UPDATED`, `DAY_NOTES` and `CLASSES`. `STUDIOS` and `FAVORITES` are never
   touched. The favorite is matched by studio + weekday + time + title, not by date, so it keeps working every week.
4. If `index.html` changed, the workflow commits it as `github-actions[bot]`, pushes to `main`, and deploys GitHub Pages.

**Safety:** if a studio's feed errors, or returns 0 sessions when the page previously had entries for it,
the script keeps that studio's previous entries, still writes the file, and exits with code 1. The run
is then marked failed, and GitHub emails the repo owner. The script never publishes a schedule with no
studio classes at all.

GitHub Pages is set to **"GitHub Actions"** as its source. `.github/workflows/pages.yml` deploys on every
manual push to `main`, and the weekly workflow deploys its own commit.

### Run it manually

- On GitHub: **Actions → Weekly schedule update → Run workflow**, or `gh workflow run weekly-update.yml`.
- Locally: `python3 scripts/update.py` (add `--dry-run` to only print, or `--start YYYY-MM-DD` to pick the first date).
  Then `git commit -am "Schedule update" && git push`. The push triggers the Pages deploy.

### Add a studio

1. Find its Eversports ids: `python3 scripts/update.py --discover <eversports-slug>`
   (the slug from `https://www.eversports.de/s/<slug>`). This prints the venue id and the schedule widgets
   that include that venue. Prefer a widget that covers only that venue.
2. Add `{"name": ..., "widget": ..., "venue": ...}` to `SOURCES` in `scripts/update.py`.
3. Add a matching entry (same `name`) to the `STUDIOS` array in `index.html`: address, phone, booking link,
   prices, passes. Optional `contact` is shown on the studio card when set. Only use real data from the studio.
4. Run `python3 scripts/update.py --dry-run` to check, then commit and push.

For a studio without an Eversports feed, add a weekly entry to `TEMPLATES` in the script instead.

### Little Big Ganesha (titles are not marked English)

The public schedule widget is the same shape as the other studios
(`widget` `6778be3b-3ae8-4e75-9463-e861a34ed10f`, `venue` `88d4711f-692c-49af-9580-3384d5b4c791`,
slug `little-big-ganesha`). Session titles are the German class names (`Yoga Intermediate`, `Yoga Open`, …)
with no `ENG` / bilingual marker, and the feed also contains German-only classes, workshops, retreats and
teacher training. Those must not all be published.

`SOURCES` therefore lists `slots` for the bilingual / English-friendly classes Holger described.
Weekday is **0 = Monday … 6 = Sunday** (same as `TEMPLATES`, not the JavaScript Sunday = 0 used by `FAVORITES`).
A session is kept only when weekday, start time and activity-group `name` all match a slot. It is stored as
`lang: "DE/ENG"`. Categories in `skip_categories` (Workshop, Event, Retreats, Ausbildungen, Online,
Präventionskurs) are dropped even if the clock time matches — so the Friday 18:00 retreat is not the
Friday class. A regular class whose title *does* say English is kept as well.

Current slots:

| When | Start | Activity-group name | What Holger described |
| --- | --- | --- | --- |
| Wed | 18:00 | Yoga Intermediate | Intermediate with Tori, 90 min |
| Thu | 07:30 | Yoga Open | Thursday morning |
| Thu | 19:30 | Yoga Basic, or Yoga Intermediate if one is published | Basic and intermediate |
| Fri | 18:00 | Intermediate - Start into the weekend | Friday 18:00 |
| Sun | 11:00 | Yoga Intermediate | Sunday 11:00 |

The live Thursday 19:30 session is **Yoga Basic** (beginner). There is no separate intermediate class at
that time in the feed; `Yoga Intermediate` is listed so it is picked up if the studio publishes one.
Teachers and end times come from the feed (Tori is the usual Wednesday teacher, not a hard filter).

If the studio renames a class, the slot stops matching. The script then keeps that studio's previous
entries and exits 1, same as a feed error. Update the `names` list and re-run.

If titles later include `ENG` / `DE/ENG` / `bilingual`, you can delete `slots` and `skip_categories` and
this studio will use the same title filter as the others.

There is no static `TEMPLATES` fallback for this studio while the feed works. Add one only if the widget
itself goes away: one `TEMPLATES` row per slot above, `lang: "DE/ENG"`, `type: "Yoga"`, with the usual
start/end (Wed 18:00–19:30, Thu 07:30–08:30, Thu 19:30–20:45, Fri 18:00–19:30, Sun 11:00–12:15).

## Data format (if you edit by hand)

```js
{ date:"2026-10-05", start:"20:00", end:"21:30", studio:"Balance Yoga Mainz",
  name:"Advanced Asana Flow (engl.)", level:"Advanced", teacher:"Taisiia R.", lang:"ENG", type:"Yoga" }
```

- `date` is ISO `YYYY-MM-DD`. `start`/`end` are 24h `HH:MM`, with `end:""` if unknown.
- `studio` must exactly match a `name` in `STUDIOS`. That's how the Book button gets its link.
- `level` is `Beginner`, `Intermediate`, `Advanced`, `All levels` or `""`. Eversports "professional" maps to Advanced.
- `lang` is `ENG`, `DE/ENG` or `English not confirmed`. The latter is hidden by *Hide unconfirmed English*.
- `type` is `Yoga`, `Pilates`, `Reformer Pilates` or `Strength`. Non-yoga classes are hidden while *Yoga only* is on (the default).
- `cancelled:true` is optional. It shows the class struck through.
- `DAY_NOTES` maps a date to a warning (holidays). `FAVORITES` matches studio + weekday (0=Sun) + start + name.

## Rules

- Yoga schedule only. Never add medical or personal appointments. Don't invent classes, prices or phone numbers.
- Keep `<meta name="robots" content="noindex">`.
