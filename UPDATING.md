# Updating the schedule each week

The whole site is one file: `index.html`. All data lives in a single block at the
top of the `<script>` tag, between these two comments:

```
/* =====================================================================
   DATA — the weekly update job replaces ONLY this block.
   ...
/* ======================== END OF DATA ================================ */
```

Replace only what is between those markers. Leave the rendering code below untouched.

## What to update

1. **`LAST_UPDATED`**: a readable string, e.g. `"Sun 4 Oct 2026, 22:00 (Berlin time)"`.
2. **`CLASSES`**: one object per class, for the next two weeks (Monday to Sunday):
   ```js
   { date:"2026-10-05", start:"20:00", end:"21:30", studio:"Balance Yoga Mainz",
     name:"Advanced Asana Flow (engl.)", level:"Advanced", teacher:"Taisiia R.", lang:"ENG" }
   ```
   - `date`: ISO `YYYY-MM-DD`. `start`/`end`: 24h `HH:MM`. Use `end:""` if unknown.
   - `studio`: must exactly match a `name` in `STUDIOS` (this is how the Book button is linked).
   - `level`: `"Beginner"`, `"Intermediate"`, `"Advanced"`, `"All levels"`, or `""` if not stated.
   - `teacher`: `""` if unknown.
   - `lang`: `"ENG"`, `"DE/ENG"`, or `"English not confirmed"`. Anything containing
     "not confirmed" is hidden by the *Hide unconfirmed English* toggle.
   - Order doesn't matter. The page sorts by date and time.
3. **`STUDIOS`**: only change this when a studio's details change. Fields are `name` (short, used in
   filters/cards), `fullName`, `address`, `phone` (`""` if unknown), `email`, `booking` (Eversports URL,
   or `""` to show Email/Call buttons instead), `prices`, `passes`.
4. **`DAY_NOTES`**: optional warnings per date, e.g. public holidays:
   `{ "2026-10-03": "German Unity Day (public holiday) – classes may not run." }`.
   Remove dates that are in the past.
5. **`FAVORITES`**: matched by `studio` + `weekday` (0=Sun … 6=Sat) + `start` + `name`.
   These get the ★ highlight and show up under the *Favorites* filter.

## Rules

- Only yoga classes taken from the studios' Eversports calendars (or the studio's own site for PRAXYS).
  Don't invent classes, prices or phone numbers, and never add medical or personal appointments.
- Keep `<meta name="robots" content="noindex">` in the page head.

## How the weeks work

Weeks run Monday to Sunday. "This week" means the current week, or the first week in the data if today
is before it. "Next week" is the week after that. Weeks that are already over are hidden automatically.

## Check and publish

```bash
google-chrome --headless=new --no-sandbox --user-data-dir=/tmp/yc --dump-dom file://$PWD/index.html | grep -c 'class="card'
git add index.html && git commit -m "Schedule update <dates>" && git push origin main
```

GitHub Pages usually refreshes within 1–2 minutes: https://bowtiedcontract.github.io/english-yoga-wiesbaden/
