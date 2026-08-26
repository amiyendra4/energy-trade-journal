# Energy Trade Journal — Cloud Version

A Streamlit trade journal designed for two types of access:

- **Trader:** username/password protected and can add, edit, close, delete trades and edit weekly notes.
- **Mentor:** opens a secret link with no username/password and gets a strictly read-only journal.

The app keeps the Excel-style architecture:

1. **01 — Trade Data**
2. **02 — Weekly Review**
3. **03 — Monthly Review**
4. **Weekly Notes**

Trade records include **LIVE/CLOSED status, Entry Idea, Exit Idea, Exit Reason, multiple entry fills, weighted-average entry, targets/stops, PnL and remarks**.

---

## 1. How the database works

- If `DATABASE_URL` is present, the app uses **PostgreSQL** (recommended: Supabase).
- If `DATABASE_URL` is absent, it automatically uses **local SQLite** so you can still test on your PC.
- The cloud database schema is created automatically on the first app start.

For the real shared journal, use Supabase/PostgreSQL. Do not rely on SQLite for Streamlit Cloud because local app storage is not the right persistent shared database for this use case.

---

## 2. Local test on Windows

Open PowerShell inside the inner `energy_trade_journal` folder where `app.py` is located.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m streamlit run app.py
```

Without a secrets file, local development defaults are:

- Username: `trader`
- Password: `trade123`

These defaults are only for local testing. Set your own credentials before deploying online.

---

# ONLINE DEPLOYMENT — STEP BY STEP

## Step 1 — Create a Supabase project

1. Go to **Supabase** and create/sign in to your account.
2. Create a **New project**.
3. Choose a project name such as `energy-trade-journal`.
4. Create a strong database password and save it somewhere secure.
5. Wait for the database to finish provisioning.

You do **not** need to manually create the trade tables. The app creates its tables automatically when it first connects.

## Step 2 — Copy the PostgreSQL connection string

In your Supabase project:

1. Click **Connect**.
2. Find a PostgreSQL connection string.
3. For Streamlit Cloud, the **transaction pooler** connection is a practical option.
4. Copy the full URI and replace the password placeholder with your real database password.

It will look broadly like:

```text
postgresql://postgres.PROJECT_REF:YOUR_PASSWORD@aws-REGION.pooler.supabase.com:6543/postgres
```

Do not put this connection string directly in `app.py` or commit it to GitHub.

## Step 3 — Generate your mentor secret token

Run this once in PowerShell:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copy the output. This becomes the secret part of the mentor link.

## Step 4 — Choose your trader login

Choose your own username and a strong password. Example only:

```text
JOURNAL_TRADER_USER = "suraj"
JOURNAL_TRADER_PASS = "use-your-own-strong-password"
```

Do not use the example password in production.

## Step 5 — Optional: test Supabase locally first

Copy:

```text
.streamlit/secrets.toml.example
```

to:

```text
.streamlit/secrets.toml
```

Then fill it with your real values:

```toml
DATABASE_URL = "YOUR_SUPABASE_POSTGRES_CONNECTION_STRING"
JOURNAL_TRADER_USER = "YOUR_USERNAME"
JOURNAL_TRADER_PASS = "YOUR_PASSWORD"
JOURNAL_MENTOR_TOKEN = "YOUR_RANDOM_MENTOR_TOKEN"
```

`secrets.toml` is already excluded by `.gitignore`. Never upload it publicly.

Restart the app:

```powershell
python -m streamlit run app.py
```

After login, the sidebar should say:

```text
Database: PostgreSQL / Supabase
```

If it says `SQLite (local development)`, the `DATABASE_URL` secret has not been loaded.

## Step 6 — Put the project on GitHub

Create a GitHub repository, for example:

```text
energy-trade-journal
```

Upload the **contents of the inner `energy_trade_journal` folder** so `app.py` is at the repository root.

The repository should contain:

```text
app.py
database.py
requirements.txt
README.md
.gitignore
.streamlit/
    config.toml
    secrets.toml.example
```

It must **not** contain your real `.streamlit/secrets.toml`.

## Step 7 — Deploy on Streamlit Community Cloud

1. Sign in to Streamlit Community Cloud using GitHub.
2. Click **Create app**.
3. Select your GitHub repository.
4. Branch: normally `main`.
5. Main file path: `app.py`.
6. Open **Advanced settings**.
7. Choose a supported Python version. Python 3.12 or 3.13 is suitable for this project.
8. In **Secrets**, paste:

```toml
DATABASE_URL = "YOUR_SUPABASE_POSTGRES_CONNECTION_STRING"
JOURNAL_TRADER_USER = "YOUR_USERNAME"
JOURNAL_TRADER_PASS = "YOUR_STRONG_PASSWORD"
JOURNAL_MENTOR_TOKEN = "YOUR_RANDOM_MENTOR_TOKEN"
```

9. Click **Deploy**.

The first startup may take a little longer because the app will create the database tables.

## Step 8 — Your trader link

Your normal Streamlit URL will look like:

```text
https://your-app-name.streamlit.app
```

Open this URL. You will see the trader login page and must enter your username/password.

## Step 9 — Mentor no-login link

Your mentor link is:

```text
https://your-app-name.streamlit.app/?mentor=YOUR_RANDOM_MENTOR_TOKEN
```

You can also log in as Trader, then use **Open Mentor Read-Only View** in the sidebar and copy the resulting URL.

The mentor sees the journal immediately with no username/password.

### Important security rule

The mentor URL is effectively a secret viewing key. **Anyone who gets that full URL can view the journal.** Do not post it publicly or forward it to people who should not have access. If the URL is ever exposed, generate a new token and change `JOURNAL_MENTOR_TOKEN` in Streamlit Cloud secrets.

## Step 10 — Confirm mentor permissions

Test the mentor link yourself in an incognito/private browser window. Confirm that the mentor can:

- View Trade Data
- View Weekly Review
- View Monthly Review
- View Weekly Notes

and cannot:

- Add a trade
- Edit a trade
- Close a trade
- Delete a trade
- Edit/save weekly notes

## Step 11 — Daily workflow

**You:**

```text
Streamlit URL → Trader login → Add/Edit/Close trades → Supabase saves changes
```

**Mentor:**

```text
Secret mentor URL → No login → Read-only journal → sees the same Supabase data
```

Your PC does not need to remain switched on for your mentor to access the deployed journal.

---

## Changing your login later

Open the deployed Streamlit app settings and update:

```toml
JOURNAL_TRADER_USER = "new_username"
JOURNAL_TRADER_PASS = "new_password"
```

Then save/reboot the app.

## Revoking the mentor link

Generate a new token:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Replace `JOURNAL_MENTOR_TOKEN` in Streamlit Cloud secrets. The old mentor link stops working after the app reloads.

---

## Troubleshooting

### `No module named streamlit`

```powershell
pip install -r requirements.txt
```

### `requirements.txt` not found

You are probably in the outer extracted ZIP folder. Run:

```powershell
dir
```

and enter the inner `energy_trade_journal` folder before running installation commands.

### App shows SQLite instead of PostgreSQL

Check that `DATABASE_URL` exists in `.streamlit/secrets.toml` locally or in Streamlit Cloud **App settings → Secrets** online.

### Database connection error

Re-copy the connection URI from Supabase **Connect**, verify the password, and make sure special characters in the password are URL-encoded if necessary.

### Mentor sees login screen

The URL must contain the exact token:

```text
?mentor=YOUR_TOKEN
```

and `YOUR_TOKEN` must exactly match `JOURNAL_MENTOR_TOKEN` in Streamlit secrets.
