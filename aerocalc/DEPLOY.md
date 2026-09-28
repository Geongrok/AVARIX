# Deploying AeroCalc for free

You want a public URL anyone can open — not `localhost`, not same-Wi-Fi. Two
routes below are genuinely free and need no credit card.

Everything the deployment needs is already in this project: `wsgi.py`,
`Procfile`, `render.yaml`, `.gitignore`, and `gunicorn` in `requirements.txt`.

**Which to pick.** If the point is to send your professor a link that opens
instantly, use **PythonAnywhere** — nothing sleeps. If you want a proper
Git-based deployment that redeploys when you push, use **Render** — but the
free tier sleeps after 15 minutes and the first visit then takes about a
minute to wake.

---

## Option A — PythonAnywhere (no cold start)

No Git, no Docker. NumPy, SciPy and Matplotlib are already installed on their
servers, which sidesteps the build-size problem this app would otherwise hit.

1. Sign up at [pythonanywhere.com](https://www.pythonanywhere.com/) — the free
   "Beginner" account.
2. **Files** tab → upload the project. Easiest is to upload the zip and then
   open a **Bash console** and run `unzip aerocalc.zip`. You should end up with
   `/home/YOURNAME/aerocalc/app.py`.
3. In that Bash console, install Flask into your account:
   ```bash
   pip3.12 install --user Flask
   ```
   NumPy, SciPy and Matplotlib are already there. You do **not** need gunicorn:
   PythonAnywhere runs the app itself.
4. **Web** tab → *Add a new web app* → *Manual configuration* → Python 3.12.
5. On that page, find **WSGI configuration file** and click it. Delete
   everything in it and replace with:
   ```python
   import sys

   path = "/home/YOURNAME/aerocalc"          # <- your actual username
   if path not in sys.path:
       sys.path.insert(0, path)

   from app import app as application
   ```
6. Still on the **Web** tab, set **Source code** to `/home/YOURNAME/aerocalc`.
7. Click the big green **Reload** button.

Your site is live at `https://YOURNAME.pythonanywhere.com`.

**The one thing to remember:** free web apps expire after a month. You get an
email, and there is a button on the Web tab to renew. If nobody clicks it the
site goes offline — so renew it before a demo, not after.

---

## Option B — Render (Git-based, auto-redeploys)

1. Put the project on GitHub. In the project folder:
   ```bash
   git init
   git add .
   git commit -m "AeroCalc"
   ```
   Create an empty repo on GitHub, then follow the two commands it shows you
   to push.
2. Sign up at [render.com](https://render.com/) with your GitHub account.
3. **New → Web Service**, pick the repo. Because `render.yaml` is in the repo,
   Render fills in the settings itself. If it asks anyway:
   - **Runtime:** Python 3
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `gunicorn wsgi:application --workers 1 --threads 4 --timeout 120`
   - **Instance type:** Free
4. Create the service and watch the log. The first build takes 3–5 minutes
   because SciPy and Matplotlib are large.

Your site is live at `https://YOUR-SERVICE.onrender.com`.

**Two things that trip people up.** The free instance has 512 MB of RAM, and
NumPy + SciPy + Matplotlib take about 200 MB of it — that is why the start
command says `--workers 1`. A second worker doubles the baseline and gets the
process killed. And free services sleep after 15 minutes idle, so the first
visitor after a quiet spell waits about a minute while Render shows a loading
page. Open the link yourself a minute before showing anyone.

---

## Why the start command looks like that

```
gunicorn wsgi:application --workers 1 --threads 4 --timeout 120
```

- `--workers 1` — memory, as above.
- `--threads 4` — lets the server handle several visitors at once without a
  second process.
- `--timeout 120` — some calculators render several charts; the 30-second
  default can kill a legitimate request on a slow free instance.

Chart rendering is serialised behind a lock in `app.py`. Matplotlib is not
thread-safe — its mathtext parser, used for logarithmic axis labels, corrupts
under concurrent access and fails part way through drawing. This was found by
stress-testing the real server, not assumed: 48 simultaneous chart-heavy
requests now return 200 with no errors, peaking at about 200 MB.

---

## Checking it worked

Once deployed, from any machine:

```bash
curl -s https://YOUR-URL/api/catalog | head -c 200
```

You should see JSON listing the nine disciplines. Then open the URL in a
browser, pick a calculator, and press Calculate — if a chart appears, the whole
stack is working.

---

## What not to bother trying

- **Vercel and Netlify** are built for static sites and small serverless
  functions. SciPy and Matplotlib blow past the bundle size limits.
- **Hugging Face Spaces** now requires a paid plan to create Docker or Gradio
  Spaces on a personal account. Only static Spaces remain free, which will not
  run Flask.
- **GitHub Pages** serves static files only and cannot run Python at all.
