# Email Summarize Agent

> An always-on AI agent that watches a Microsoft 365 inbox, understands every new email (and PDF attachment) using **Google Gemini**, and delivers a clean, founder-friendly briefing straight to **WhatsApp** within seconds.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Microsoft Graph](https://img.shields.io/badge/Microsoft%20Graph-API-0078D4?logo=microsoft)
![Gemini](https://img.shields.io/badge/Google-Gemini-4285F4?logo=google)
![Twilio](https://img.shields.io/badge/Twilio-WhatsApp-F22F46?logo=twilio&logoColor=white)
![Railway](https://img.shields.io/badge/Deploy-Railway-0B0D0E?logo=railway)
![Status](https://img.shields.io/badge/status-production-success)
![License](https://img.shields.io/badge/license-MIT-blue)

---

## Table of contents

1. [Business use case](#business-use-case)
2. [Features](#features)
3. [Architecture](#architecture)
4. [Tech stack](#tech-stack)
5. [Sample output](#sample-output)
6. [Prerequisites](#prerequisites)
7. [Local setup](#local-setup)
8. [Environment variables](#environment-variables)
9. [Running locally](#running-locally)
10. [Cloud deployment](#cloud-deployment)
11. [Project structure](#project-structure)
12. [How it works (deep dive)](#how-it-works-deep-dive)
13. [Spam filtering](#spam-filtering)
14. [Self-monitoring & alerts](#self-monitoring--alerts)
15. [Troubleshooting](#troubleshooting)
16. [Roadmap](#roadmap)
17. [Author](#author)
18. [License](#license)

---

## Business use case

Founders, CEOs, and operations leads receive **hundreds of emails per day** — invoices, partnership pitches, vendor updates, payment confirmations, HR escalations, customer support tickets — and most of the day is lost just **triaging** the inbox. Opening every mail to figure out which one needs action is slow, draining, and expensive in opportunity cost.

This agent solves that problem.

**The user never has to open their inbox again.**

Every new email is read, classified, and condensed into a 5–6 line WhatsApp briefing on their phone — formatted exactly the way a busy decision-maker wants to read it. PDF attachments (contracts, invoices, statements) are read end-to-end and the key numbers / terms / dates are pulled into the same briefing, with the original PDF attached.

Built originally as a freelance project for a startup founder who wanted to **reclaim 2–3 hours a day** spent on email triage.

**Who this is for:**
- Founders and CEOs who live on WhatsApp
- Executive assistants managing multiple inboxes
- Operations teams who need real-time visibility into vendor / partner emails
- Anyone who treats their inbox as a notification stream rather than a workspace

---

## Features

- **Real-time email monitoring** — polls Microsoft 365 inbox every 30 seconds via Microsoft Graph API
- **AI summarization** — uses Google Gemini Flash to produce structured, category-tagged briefings
- **Auto-categorization** — classifies every email into one of: Payments, Vendor, Updates, HR, Partnership, Legal, Customer, Operations, Marketing, Other
- **PDF understanding** — extracts text from PDF attachments and summarizes the actual contents (numbers, terms, deadlines), not just the file name
- **Link extraction** — pulls every URL out of the email body and surfaces them in a dedicated section
- **WhatsApp delivery** — sends the briefing to the user's WhatsApp via Twilio, with PDFs attached inline
- **Smart spam filter** — silently skips a configurable list of known noise senders (newsletters, billing receipts, automated notifications)
- **Time-aware greeting** — opens every message with "Good Morning / Afternoon / Evening" based on IST
- **Self-monitoring** — alerts the user on WhatsApp if Gemini quota is exhausted, Twilio balance runs out, Azure auth fails, or the internet drops
- **Safe character handling** — automatically truncates messages over the Twilio 1600-character WhatsApp limit
- **Production-tested** — runs 24/7 as a Railway worker with auto-recovery on transient failures

---

## Architecture

```
   ┌────────────────────────┐
   │   Microsoft 365 Inbox  │
   │   (any mailbox in your │
   │    Azure tenant)       │
   └───────────┬────────────┘
               │ Graph API — poll every 30s
               │ filter: unread, received after agent start
               ▼
   ┌────────────────────────┐
   │       agent.py         │
   │  ────────────────────  │
   │  1. Fetch new emails   │
   │  2. Skip spam senders  │
   │  3. Read body + links  │
   │  4. Download PDFs      │
   │  5. Extract PDF text   │
   └─────┬────────────┬─────┘
         │            │
         │            └──────────────┐
         ▼                           ▼
  ┌────────────────┐        ┌─────────────────────┐
  │  Google Gemini │        │   File host         │
  │  Flash         │        │   tmpfiles.org →    │
  │                │        │   gofile.io →       │
  │  Structured    │        │   file.io           │
  │  summary       │        │   (fallback chain)  │
  └────────┬───────┘        └──────────┬──────────┘
           │  WhatsApp-formatted text  │  public PDF URL
           └─────────────┬─────────────┘
                         ▼
                ┌────────────────┐
                │  Twilio        │
                │  WhatsApp API  │
                └────────┬───────┘
                         ▼
              ┌────────────────────┐
              │  Founder's phone   │
              │  (WhatsApp)        │
              └────────────────────┘

  Self-monitoring: any failure (Gemini quota, Twilio balance,
  Azure auth, no internet) is sent as a system alert to the
  same WhatsApp number.
```

---

## Tech stack

| Layer | Technology | Why |
|---|---|---|
| Language | Python 3.10+ | Mature SDKs for every integration |
| Email source | Microsoft Graph API | Works with any M365 mailbox; uses app-only OAuth (no user password) |
| Auth | Azure AD client-credentials flow | Stateless, no token refresh needed |
| Summarization | Google Gemini `gemini-flash-latest` | Cheap, fast, generous free tier, strong instruction following |
| Messaging | Twilio WhatsApp API | Reliable global delivery, supports media attachments |
| PDF parsing | PyPDF2 | Pure-Python, no system dependencies |
| File hosting | tmpfiles.org → gofile.io → file.io | Three-step fallback chain so PDFs always land |
| Scheduler | Native Python `time.sleep` loop | Single-process worker, no extra infra |
| Deployment | Railway (Procfile) | One-click long-lived worker, easy env-var management |
| Secrets | python-dotenv + `.env` | Standard, gitignored |

---

## Sample output

A real WhatsApp message produced by the agent:

```
Good Morning!

*Payments* | FYI: Stripe sent Invoice #INV-9201 paid

*Key Points:*
• Customer "Acme Inc." paid Rs. 84,500 on 14 May
• Net after Stripe fees: Rs. 82,180
• Funds settle to account on 16 May
• Linked subscription: Annual / Pro tier

*Links:*
https://dashboard.stripe.com/invoices/in_1Nq...
```

For PDF attachments (e.g. a vendor contract), the briefing summarizes the **contents of the PDF** — pricing, terms, deadlines — not just the filename, and the original PDF is delivered as a WhatsApp attachment in the same message.

---

## Prerequisites

You will need accounts on four services. All have free tiers sufficient for testing.

| Service | What you need | Where to get it |
|---|---|---|
| **Python** | 3.10 or newer | python.org |
| **Microsoft Azure** | An App Registration with `Mail.Read` (Application) permission, admin-consented | portal.azure.com → Azure Active Directory → App registrations |
| **Google Gemini** | A free API key | aistudio.google.com/app/apikey |
| **Twilio** | Account SID, Auth Token, and a WhatsApp sender (the sandbox is fine to start) | console.twilio.com |
| **Git** | Any recent version | git-scm.com |

> Estimated setup time: **30–45 minutes** the first time (mostly waiting for Azure admin consent).

---

## Local setup

### 1. Clone the repository

```bash
git clone https://github.com/PJDEEPESH/EmailSummarizeAgent.git
cd EmailSummarizeAgent
```

### 2. Create a virtual environment

**Windows (PowerShell):**
```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure your secrets

Copy the template:

```bash
# Windows
copy .env.example .env
# macOS / Linux
cp .env.example .env
```

Open `.env` and fill in your values (see [Environment variables](#environment-variables) below).

---

## Environment variables

All variables live in a `.env` file at the project root. **Never commit this file** — it is gitignored.

| Variable | Required | Description |
|---|---|---|
| `TENANT_ID` | yes | Azure AD tenant ID (Directory ID) of the M365 organization |
| `CLIENT_ID` | yes | Application (client) ID of the Azure App Registration |
| `CLIENT_SECRET` | yes | Client secret value from the App Registration |
| `EMAIL_TO_WATCH` | yes | The mailbox to monitor, e.g. `founder@company.com` |
| `GEMINI_API_KEY` | yes | Google Gemini API key from AI Studio |
| `TWILIO_SID` | yes | Twilio Account SID (starts with `AC...`) |
| `TWILIO_TOKEN` | yes | Twilio Auth Token |
| `FROM_WHATSAPP` | yes | Twilio WhatsApp sender, e.g. `whatsapp:+14155238886` |
| `TO_WHATSAPP` | yes | Recipient WhatsApp number, e.g. `whatsapp:+91XXXXXXXXXX` |

### How to get each value

**Azure (`TENANT_ID`, `CLIENT_ID`, `CLIENT_SECRET`)**
1. Go to **portal.azure.com → Azure Active Directory → App registrations → New registration**
2. Name it `EmailSummarizeAgent`, leave defaults, click **Register**
3. Copy the **Directory (tenant) ID** → `TENANT_ID`
4. Copy the **Application (client) ID** → `CLIENT_ID`
5. Go to **Certificates & secrets → Client secrets → New client secret** → copy the **Value** (not the ID) → `CLIENT_SECRET`
6. Go to **API permissions → Add a permission → Microsoft Graph → Application permissions → `Mail.Read`**
7. Click **Grant admin consent** (you need to be an admin, or ask one)

**Gemini (`GEMINI_API_KEY`)**
1. Go to **aistudio.google.com/app/apikey**
2. Click **Create API key** → copy it

**Twilio (`TWILIO_SID`, `TWILIO_TOKEN`, `FROM_WHATSAPP`, `TO_WHATSAPP`)**
1. Sign up at **twilio.com** (free trial gives you $15 credit)
2. Copy the **Account SID** and **Auth Token** from the Console dashboard
3. For `FROM_WHATSAPP`: enable the WhatsApp sandbox at **Messaging → Try it out → Send a WhatsApp message** — the sender number is `whatsapp:+14155238886`
4. Join the sandbox from your phone (send the join code to that number on WhatsApp)
5. `TO_WHATSAPP` is your own WhatsApp number prefixed with `whatsapp:` and the country code, e.g. `whatsapp:+919581571616`

---

## Running locally

With your `.env` filled in and venv activated:

```bash
python agent.py
```

Expected output:

```
[START] Email Agent Running 24/7...
[INFO] Watching: founder@company.com
[INFO] Only processing emails after: 2026-05-24T10:32:00Z
```

Send yourself a test email to the watched mailbox. Within ~30 seconds you should see:

```
[NEW] Test Sender <you@gmail.com>
[SUBJECT] Test email
[SUMMARY]
Good Morning!
...
[SUCCESS] WhatsApp sent!
```

And the WhatsApp briefing should land on your phone.

> **Tip:** the agent only processes emails received **after** it started. Older unread emails are ignored on purpose, so you don't get a flood of summaries on first launch.

---

## Cloud deployment

The agent is a **long-lived worker** (not a web server), so it needs a host that runs a persistent process. The repo includes a `Procfile`:

```
worker: python agent.py
```

### Option 1 — Railway (recommended, easiest)

1. Push the repo to GitHub
2. Go to **railway.app → New Project → Deploy from GitHub repo** → select this repo
3. In the **Variables** tab, paste in every variable from `.env.example` with your real values
4. Railway auto-detects the `Procfile` and runs `worker: python agent.py`
5. Open the **Logs** tab to confirm `[START] Email Agent Running 24/7...`

Cost: free tier is enough for low-volume mailboxes. ~$5/month on the Hobby plan for unlimited runtime.

### Option 2 — Render

1. Push the repo to GitHub
2. **render.com → New → Background Worker** → connect the repo
3. Build command: `pip install -r requirements.txt`
4. Start command: `python agent.py`
5. Add every env var under **Environment**

### Option 3 — Any VPS (DigitalOcean, AWS EC2, Hetzner)

```bash
# On the server
git clone https://github.com/PJDEEPESH/EmailSummarizeAgent.git
cd EmailSummarizeAgent
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# Create .env with your values

# Run under systemd or pm2 so it auto-restarts
pm2 start "python agent.py" --name email-agent
pm2 save
pm2 startup
```

### Option 4 — Docker (build your own)

The project doesn't ship a Dockerfile out of the box, but a minimal one is just:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "agent.py"]
```

---

## Project structure

```
EmailSummarizeAgent/
├── agent.py            # The entire agent — poll, filter, summarize, send
├── requirements.txt    # Python dependencies (requests, twilio, dotenv, PyPDF2, pytz)
├── Procfile            # Railway / Heroku worker definition
├── .env.example        # Template for required environment variables
├── .env                # Your real secrets (gitignored, NEVER commit)
├── .gitignore          # Excludes .env, venv, __pycache__, IDE folders
└── README.md           # This file
```

---

## How it works (deep dive)

The whole agent is ~470 lines in a single file, [`agent.py`](agent.py). The main loop:

1. **Get an Azure access token** via OAuth2 client-credentials flow ([`get_access_token`](agent.py#L109))
2. **Fetch unread emails** received after the agent's start time ([`get_new_emails`](agent.py#L125))
3. **Skip ignored senders** by checking `IGNORED_SENDERS` set ([`agent.py:40`](agent.py#L40))
4. **For each new email:**
   - Extract URLs from the body ([`extract_links`](agent.py#L69))
   - Download attachments and extract PDF text ([`get_attachments_content`](agent.py#L138))
   - Build a structured Gemini prompt with strict formatting rules ([`summarize_with_gemini`](agent.py#L176))
   - Upload any PDFs to a public host with a 3-step fallback chain ([`upload_pdf_for_whatsapp`](agent.py#L262))
   - Send the summary + PDF to WhatsApp via Twilio ([`send_whatsapp`](agent.py#L326))
   - Mark the email as read so it isn't processed twice ([`mark_as_read`](agent.py#L359))
5. **Sleep 30 seconds, repeat.**

Failures at any step are caught, counted, and (on the first or third occurrence depending on type) reported back to the same WhatsApp number as a system alert — so you find out about a broken integration before the founder does.

---

## Spam filtering

The `IGNORED_SENDERS` set at the top of [`agent.py`](agent.py#L40) holds email addresses to silently skip. Newsletters and automated senders go here. Add new senders as you encounter them — lowercase, exact match.

```python
IGNORED_SENDERS = {
    "noreply@mail.iaapa.org",
    "dailynewsletter@iaapa.org",
    "info@e.atlassian.com",
    ...
}
```

Filtered emails are marked-as-read but never summarized or sent to WhatsApp.

---

## Self-monitoring & alerts

The agent watches itself. If something breaks, a `*[SYSTEM ALERT]*` message goes to the same WhatsApp number:

| Trigger | Alert title |
|---|---|
| Gemini returns 429 / `RESOURCE_EXHAUSTED` | Gemini API Quota Exhausted |
| Gemini returns 401 / 403 | Gemini API Key Invalid |
| Twilio error code 21608 / "insufficient" / "balance" | Twilio Balance Finished |
| Twilio error code 21211 / "invalid" | Twilio Invalid Number |
| Azure auth fails (bad `CLIENT_SECRET` etc.) | Azure Auth Failed |
| 3 consecutive `ConnectionError`s | No Internet |
| Any other unhandled exception | Agent Error |

This means you never have to babysit logs — broken integrations announce themselves.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Azure auth failed` on startup | Wrong `TENANT_ID` / `CLIENT_ID` / `CLIENT_SECRET`, or admin consent not granted | Double-check the three values; re-grant admin consent for `Mail.Read` |
| Emails fetched but no WhatsApp arrives | Twilio sandbox not joined from your phone | Send the join code (e.g. `join <two-words>`) to `+14155238886` on WhatsApp |
| WhatsApp says "Message truncated" | Email body or PDF was too long (>1500 chars after summarization) | This is expected — Twilio has a hard 1600-char limit for WhatsApp |
| PDF attachment not delivered | All three upload hosts failed | Check internet; verify tmpfiles.org / gofile.io / file.io aren't blocked |
| `Gemini API Quota Exhausted` alert | Free tier rate limit hit | Wait an hour, or upgrade your Gemini plan |
| Newsletter / spam is being summarized | Sender not in `IGNORED_SENDERS` | Add the sender email (lowercase) to the set and redeploy |

---

## Roadmap

Things that could be added but aren't (yet):

- Reply-from-WhatsApp (use Gemini to draft a reply and let the user approve via WhatsApp)
- Multi-mailbox support (one agent watching N mailboxes for N users)
- Calendar awareness (skip summarizing emails when the user is in a meeting)
- Slack / Telegram / Discord output adapters
- Per-sender priority routing (urgent senders get a separate "URGENT" prefix)
- Web dashboard for managing the ignore list

---

## Author

Built by **Deepesh PJ** as a freelance project for a startup founder, then open-sourced as a portfolio piece.

If this helped you or you have feedback, feel free to open an issue or reach out.

---

## License

MIT — see [LICENSE](LICENSE) if present, or treat this as MIT-licensed (use freely, attribution appreciated).
