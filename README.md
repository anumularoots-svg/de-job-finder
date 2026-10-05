# US Data Engineer Job Finder

Live at: `https://zapkitt.com/dataenginer`

Finds US Data Engineer jobs from permitted sources, classifies W-2 status from the posting text, removes duplicates, and shows them in one dashboard. Every **Apply** button opens the original posting. Job descriptions are not copied to the site. Only short evidence quotes like "W2 only, no C2C" are shown.

```
GitHub Actions (every 2 hours)
  collector/  ── Greenhouse, Lever, Ashby (official public APIs, per company)
              ── Adzuna (official API, free key)
              ── SmartRecruiters (skipped automatically: robots.txt disallows)
      ↓ normalize → classify (W-2 / C2C / sponsorship / experience / skills)
      ↓ dedupe (company + title + state, or same URL)
  data/jobs.db (SQLite)  →  public/dataenginer/data/jobs.json + sources.json
      ↓ commit → Vercel redeploys
  zapkitt.com/dataenginer  (static dashboard)  →  [Apply ↗]  →  original job page
```

## W-2 labels

| Label | Meaning |
|---|---|
| **W-2 Confirmed** | The posting explicitly says W-2 / W2 |
| **Direct Full-Time** | Full-time role on the employer's own job board. W-2 is not stated in the posting (company employees normally get a W-2). Kept separate from Confirmed. |
| **W-2 Unknown** | Nothing reliable in the posting. Never counted as W-2. |
| **C2C / 1099** | The posting only accepts C2C / corp-to-corp / 1099. Hidden by default. |

A "contract" job is never assumed to be W-2. Sponsorship is shown only when the posting says it: *No sponsorship*, *Sponsorship mentioned*, or nothing.

## Folder structure

```
.github/workflows/collect.yml   schedule: every 2 hours + manual "Run workflow"
collector/
  companies.csv                 company job boards to collect (edit this)
  config.py                     title rules, skills, time limits
  http.py                       polite client: robots.txt check, rate limit, no login
  sources/ats.py                Greenhouse, Lever, Ashby, SmartRecruiters
  sources/adzuna.py             Adzuna
  normalize.py                  dates, US location, remote/hybrid, employment type, dedupe keys
  classify.py                   W-2 / C2C / sponsorship / experience / skills
  db.py, run.py                 SQLite storage and the pipeline
  check.py                      test a company board before adding it
  tests/                        offline tests with sample API responses
data/jobs.db                    SQLite database (updated by the workflow)
public/dataenginer/index.html   the dashboard
public/dataenginer/data/        jobs.json + sources.json (written by the collector)
vercel.json                     serves /public, /dataengineer → /dataenginer redirect
```

---

## One-time setup (about 20 minutes)

### 1. Put the code on GitHub
1. Create a new repository on github.com, for example `de-job-finder`. Private is fine.
2. Upload every file from this folder, **including the hidden `.github` folder**.
   - Easiest way with Git installed:
     ```
     cd de-job-finder
     git init -b main
     git add .
     git commit -m "Job finder"
     git remote add origin https://github.com/<you>/de-job-finder.git
     git push -u origin main
     ```
3. In the repo, go to **Settings → Actions → General → Workflow permissions** and choose **Read and write permissions**. The collector needs this to save results.

### 2. Add the Adzuna key (free)
1. Sign up at https://developer.adzuna.com and create an app. You get an **App ID** and an **App Key**.
2. In the repo, go to **Settings → Secrets and variables → Actions → New repository secret**:
   - `ADZUNA_APP_ID` = your App ID
   - `ADZUNA_APP_KEY` = your App Key

Without the key, everything else still works and Adzuna shows as "Not set up".

### 3. Run the collector once
Go to **Actions → Collect jobs → Run workflow**. After 1–3 minutes, open the run log. It prints something like:
```
Fetched 212 matching postings; dashboard now lists 164 jobs.
  Greenhouse       ok=61 jobs=120 failed=hubspot,vercel
  ...
```
Remove company tokens listed under `failed=` from `collector/companies.csv`, or fix them (see "Add companies" below).

After this, it runs by itself every 2 hours.

### 4. Deploy on Vercel
1. On https://vercel.com, click **Add New → Project** and import the GitHub repo.
2. Framework Preset: **Other**. Leave Build Command empty. Output Directory: `public` (already set in `vercel.json`).
3. Click **Deploy**. Test it at `https://<project>.vercel.app/dataenginer`.

Every collector commit triggers a new Vercel deploy automatically (about 12 a day, within the free plan).

### 5. Serve it at zapkitt.com/dataenginer (no subdomain)
Which case applies depends on where the **main** zapkitt.com site is hosted:

**A. The main zapkitt.com site is already a Vercel project.** Leave the domain on that project. In the **main site's** `vercel.json`, add these rewrites (replace `<project>`):
```json
{
  "rewrites": [
    { "source": "/dataenginer", "destination": "https://<project>.vercel.app/dataenginer" },
    { "source": "/dataenginer/:path*", "destination": "https://<project>.vercel.app/dataenginer/:path*" }
  ]
}
```
Redeploy the main site. The job finder stays a separate project, so its frequent data commits never touch your main site.

**B. zapkitt.com has no site yet.** In this project, go to **Settings → Domains → Add** and enter `zapkitt.com`. Then add the DNS records Vercel shows at your domain registrar. `zapkitt.com/` redirects to `/dataenginer` until you have a main site.

**C. The main site is hosted somewhere else (WordPress, Hostinger, Wix, etc.).** A path like `/dataenginer` can only come from the host that owns `zapkitt.com`, and most of those hosts can't proxy a path to Vercel. Your options:
- move the main site to Vercel and use case A, or
- use `jobs.zapkitt.com` instead: add it under **Domains** and create the CNAME record Vercel shows.

### 6. Optional: "Run collector now" button
In `public/dataenginer/index.html`, set:
```js
const GITHUB_REPO = "<you>/de-job-finder";
```
The button opens the GitHub Actions page, where you can press **Run workflow** (you must be signed in to GitHub).

---

## Add companies (phase 2)
1. Find a company's board: open one of its job links.
   - `boards.greenhouse.io/<token>/...` or `job-boards.greenhouse.io/<token>/...` → greenhouse
   - `jobs.lever.co/<token>/...` → lever
   - `jobs.ashbyhq.com/<token>/...` → ashby
2. Check it (optional, needs Python locally): `python -m collector.check greenhouse <token>`
3. Add a line to `collector/companies.csv`: `greenhouse,<token>,Company Name,yes`. You can do this in the GitHub web editor.

Set `enabled` to `no` to pause a company without deleting it.

## Run locally (optional)
```
pip install -r collector/requirements.txt
python -m unittest discover -s collector/tests -t .      # offline tests
python -m collector.run                                   # real collection
python -m http.server -d public 8000                      # open http://localhost:8000/dataenginer
```
Offline demo with sample data: `python -m collector.run --fixtures collector/tests/fixtures --companies collector/tests/fixtures/companies.csv --db /tmp/demo.db`

## Limitations
- **LinkedIn, Indeed, Dice, ZipRecruiter, Google Jobs, Workday and staffing firms (TEKsystems, Kforce, Apex, Insight Global, Robert Half, Randstad) are Manual.** None of them offer a permitted public API, and the collector does not scrape, log in, or get around CAPTCHAs or robots.txt. The dashboard gives filtered search links for each one.
- Most W-2 contract roles are posted on those manual sites. The automatic feed is mostly direct-employer full-time roles plus Adzuna.
- Adzuna provides only a short description snippet, so many Adzuna jobs stay **W-2 Unknown**.
- Only companies listed in `companies.csv` are collected from Greenhouse/Lever/Ashby.
- If a source changes its robots.txt to disallow access, the collector marks it Manual on the next run.
- Greenhouse jobs without `first_published` use `updated_at` and show a `~` (approximate) posting time.
- GitHub may start scheduled runs a few minutes late. GitHub also pauses schedules in repos with no activity for 60 days, but the collector's own commits count as activity.
- The application tracker is saved in your browser. It is not synced across devices, so use **Copy CSV** for backups.
