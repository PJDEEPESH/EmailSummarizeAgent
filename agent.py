import os
import re
import sys
import base64
import io
import requests
import time
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from datetime import datetime, timezone
import pytz
from dotenv import load_dotenv
import PyPDF2

# Fix Windows terminal Unicode issues
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

load_dotenv()

print("hello world") # Added for demonstration purposes

# ========== CREDENTIALS FROM .env ==========
TENANT_ID     = os.environ.get("TENANT_ID")
CLIENT_ID     = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
EMAIL_TO_WATCH = os.environ.get("EMAIL_TO_WATCH", "deepesh.j@strikin.com")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TWILIO_SID    = os.environ.get("TWILIO_SID")
TWILIO_TOKEN  = os.environ.get("TWILIO_TOKEN")
FROM_WHATSAPP = os.environ.get("FROM_WHATSAPP", "whatsapp:+14155238886")
TO_WHATSAPP   = os.environ.get("TO_WHATSAPP")
# =============================================

seen_ids = set()

# ──────────────────────────────────────────────
#  IGNORED SENDERS (Spam / Newsletters)
# ──────────────────────────────────────────────
IGNORED_SENDERS = {
    "noreply@mail.iaapa.org",
    "info@e.atlassian.com",
    "taylor.griggs@glean.com",
    "evelinawahlstrom@sanity.io",
    "no-reply@razorpay.com",
    "team@mail.clickup.com",
    "hello@news.railway.app",
    "invoice+statements@vercel.com",
    "support@msg91.com",
    "fred@fireflies.ai"
}

# ──────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────

def get_greeting():
    """Good Morning / Afternoon / Evening based on IST."""
    ist = pytz.timezone("Asia/Kolkata")
    hour = datetime.now(ist).hour
    if hour < 12:
        return "Good Morning"
    elif hour < 17:
        return "Good Afternoon"
    else:
        return "Good Evening"


def extract_links(text):
    """Extract unique http/https URLs from text."""
    urls = re.findall(r'https?://[^\s<>"\'()]+', text)
    seen, unique = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique


def extract_pdf_text(content_bytes):
    """Read text from PDF bytes."""
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(content_bytes))
        return "".join(p.extract_text() or "" for p in reader.pages).strip()
    except Exception as e:
        print(f"[PDF ERROR] {e}")
        return ""


# ──────────────────────────────────────────────
#  ALERT — send a system alert to WhatsApp
# ──────────────────────────────────────────────

def send_alert(title, detail):
    """Send a system-level warning to the founder's WhatsApp."""
    msg = f"*[SYSTEM ALERT]*\n\n*{title}*\n{detail}\n\n_Timestamp: {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%d %b %Y, %I:%M %p IST')}_"
    try:
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        client.messages.create(body=msg, from_=FROM_WHATSAPP, to=TO_WHATSAPP)
        print(f"[ALERT SENT] {title}")
    except Exception as e:
        print(f"[ALERT FAILED] Could not send alert: {e}")


# ──────────────────────────────────────────────
#  MICROSOFT GRAPH
# ──────────────────────────────────────────────

def get_access_token():
    url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    data = {
        "grant_type":    "client_credentials",
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope":         "https://graph.microsoft.com/.default"
    }
    resp = requests.post(url, data=data, timeout=15)
    result = resp.json()
    if "access_token" not in result:
        error_desc = result.get("error_description", str(result))
        raise RuntimeError(f"Azure auth failed: {error_desc}")
    return result["access_token"]


def get_new_emails(token, start_time):
    url = f"https://graph.microsoft.com/v1.0/users/{EMAIL_TO_WATCH}/mailFolders/inbox/messages"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "$filter":  f"isRead eq false and receivedDateTime ge {start_time}",
        "$orderby": "receivedDateTime desc",
        "$top":     10,
        "$select":  "id,subject,from,bodyPreview,body,hasAttachments"
    }
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    return resp.json().get("value", [])


def get_attachments_content(token, email_id):
    """Returns list of (name, text, raw_bytes)."""
    url = f"https://graph.microsoft.com/v1.0/users/{EMAIL_TO_WATCH}/messages/{email_id}/attachments"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, timeout=20)
    attachments = resp.json().get("value", [])

    results = []
    for att in attachments:
        name         = att.get("name", "attachment")
        content_type = att.get("contentType", "")
        content_b64  = att.get("contentBytes", "")

        print(f"[ATTACHMENT] {name} ({content_type})")

        if not content_b64:
            results.append((name, "[No content]", None))
            continue

        raw = base64.b64decode(content_b64)

        if "pdf" in content_type.lower() or name.lower().endswith(".pdf"):
            text = extract_pdf_text(raw)
            results.append((name, text or "[Could not read PDF]", raw))
        elif "text" in content_type.lower() or name.lower().endswith((".txt", ".csv")):
            results.append((name, raw.decode("utf-8", errors="ignore"), None))
        elif "image" in content_type.lower():
            results.append((name, "[Image — no text]", None))
        else:
            results.append((name, f"[{content_type} — not extracted]", None))

    return results


# ──────────────────────────────────────────────
#  GEMINI SUMMARIZE
# ──────────────────────────────────────────────

def summarize_with_gemini(sender_name, sender_email, subject, body,
                          attachment_data, links, greeting):
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"gemini-flash-latest:generateContent?key={GEMINI_API_KEY}")

    att_context = ""
    for name, text, _ in attachment_data:
        att_context += f"\n\n--- Attachment: {name} ---\n{text[:3000]}"

    link_context = ("\n\nLinks found:\n" + "\n".join(links)) if links else ""

    prompt = f"""You are a smart assistant summarizing emails for a busy founder.
Use WhatsApp formatting: bold = *text* (single asterisk). Never use ** or #.

Produce the WhatsApp message in this EXACT structure — no extra text:

{greeting}!

*[CATEGORY]* | FYI: [Sender first name] sent [Short Subject]

*Key Points:*
[bullet] [point 1]
[bullet] [point 2]
[bullet] [point 3]
(max 6 bullets)

(only if links exist:)
*Links:*
[url]

STRICT RULES:
1. Line 1 = "{greeting}!" only
2. Line 2 = blank
3. Line 3 = *CATEGORY* | FYI: [First name] sent [Subject]
   CATEGORY choices: Payments, Vendor, Updates, HR, Partnership, Legal, Customer, Operations, Marketing, Other
   Auto-detect the right one from email content
4. Blank line then *Key Points:* header
5. Each bullet must use the "•" character — never * or -
6. If a PDF/doc is attached — read the document fully and summarize what is INSIDE it (numbers, terms, decisions, timelines, pricing — whatever matters most)
7. If there are links — add *Links:* section with each URL on its own line
8. Use whatever currency symbol is in the email (Rs., $, EUR, etc.) — do NOT hardcode
9. Keep every bullet under 15 words and factual
10. NO greetings repeated, NO sign-off, NO extra commentary

Email:
From: {sender_name} <{sender_email}>
Subject: {subject}
Body: {body}
{att_context}
{link_context}"""

    resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
    result = resp.json()

    # ── Error handling for Gemini ──
    if "error" in result:
        code    = result["error"].get("code", 0)
        status  = result["error"].get("status", "")
        message = result["error"].get("message", "Unknown error")

        if code == 429 or status == "RESOURCE_EXHAUSTED":
            send_alert(
                "Gemini API Quota Exhausted",
                "The Gemini AI API has run out of free quota or billing limit reached.\n"
                "Action needed: Check https://ai.dev/rate-limit and upgrade your plan."
            )
        elif code in (401, 403):
            send_alert(
                "Gemini API Key Invalid",
                f"The Gemini API key is invalid or expired.\nError: {message}"
            )
        else:
            send_alert("Gemini API Error", f"Code {code}: {message}")
        return None

    if "candidates" not in result:
        send_alert("Gemini Unexpected Response", str(result)[:300])
        return None

    return result["candidates"][0]["content"]["parts"][0]["text"]


# ──────────────────────────────────────────────
#  PDF UPLOAD
# ──────────────────────────────────────────────

def upload_pdf_for_whatsapp(content_bytes, filename):
    """Try multiple upload services and return first working public URL."""

    # ── 1. Try tmpfiles.org ──
    try:
        resp = requests.post(
            "https://tmpfiles.org/api/v1/upload",
            files={"file": (filename, content_bytes, "application/pdf")},
            timeout=20
        )
        data = resp.json()
        url = data.get("data", {}).get("url", "")
        if url:
            # tmpfiles.org returns e.g. https://tmpfiles.org/1234/file.pdf
            # Convert to direct download link
            direct = url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
            print(f"[UPLOAD] tmpfiles.org OK: {direct}")
            return direct
    except Exception as e:
        print(f"[UPLOAD] tmpfiles.org failed: {e}")

    # ── 2. Try gofile.io ──
    try:
        # First get the best server
        server_resp = requests.get("https://api.gofile.io/getServer", timeout=10)
        server = server_resp.json().get("data", {}).get("server", "store1")
        resp = requests.post(
            f"https://{server}.gofile.io/uploadFile",
            files={"file": (filename, content_bytes, "application/pdf")},
            timeout=20
        )
        data = resp.json()
        url = data.get("data", {}).get("downloadPage", "")
        if url:
            print(f"[UPLOAD] gofile.io OK: {url}")
            return url
    except Exception as e:
        print(f"[UPLOAD] gofile.io failed: {e}")

    # ── 3. Try file.io ──
    try:
        resp = requests.post(
            "https://file.io",
            files={"file": (filename, content_bytes, "application/pdf")},
            data={"expires": "1d"},
            timeout=20
        )
        if resp.text.strip():
            data = resp.json()
            url = data.get("link", "")
            if url:
                print(f"[UPLOAD] file.io OK: {url}")
                return url
    except Exception as e:
        print(f"[UPLOAD] file.io failed: {e}")

    print("[UPLOAD ERROR] All upload services failed.")
    return None


# ──────────────────────────────────────────────
#  WHATSAPP SEND
# ──────────────────────────────────────────────

def send_whatsapp(message, media_url=None):
    try:
        # Twilio WhatsApp has a strict 1600 character limit.
        if len(message) > 1500:
            message = message[:1500] + "\n\n...[Message Truncated due to length limit]"

        client = Client(TWILIO_SID, TWILIO_TOKEN)
        kwargs = dict(body=message, from_=FROM_WHATSAPP, to=TO_WHATSAPP)
        if media_url:
            kwargs["media_url"] = [media_url]
        client.messages.create(**kwargs)
        print("[SUCCESS] WhatsApp sent!")

    except TwilioRestException as e:
        msg = str(e)
        print(f"[TWILIO ERROR] {msg}")
        # Detect balance issues
        if "21608" in msg or "insufficient" in msg.lower() or "balance" in msg.lower():
            send_alert(
                "Twilio Balance Finished",
                "Your Twilio account has run out of credit.\n"
                "Action needed: Top up at https://console.twilio.com"
            )
        elif "21211" in msg or "invalid" in msg.lower():
            send_alert("Twilio Invalid Number", f"TO_WHATSAPP number may be wrong.\nError: {msg[:200]}")
        else:
            send_alert("Twilio Send Failed", msg[:300])


# ──────────────────────────────────────────────
#  MARK AS READ
# ──────────────────────────────────────────────

def mark_as_read(token, email_id):
    url = f"https://graph.microsoft.com/v1.0/users/{EMAIL_TO_WATCH}/messages/{email_id}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    requests.patch(url, headers=headers, json={"isRead": True}, timeout=10)


# ──────────────────────────────────────────────
#  MAIN LOOP
# ──────────────────────────────────────────────

def run():
    print("[START] Email Agent Running 24/7...")
    print(f"[INFO] Watching: {EMAIL_TO_WATCH}")

    start_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[INFO] Only processing emails after: {start_time}\n")

    consecutive_errors = 0

    while True:
        try:
            token  = get_access_token()
            emails = get_new_emails(token, start_time)
            consecutive_errors = 0  # reset on success

            for em in emails:
                email_id = em["id"]
                if email_id in seen_ids:
                    continue
                seen_ids.add(email_id)

                sender_email    = em["from"]["emailAddress"]["address"]
                sender_name     = em["from"]["emailAddress"].get("name", sender_email.split("@")[0])

                if sender_email.lower() in IGNORED_SENDERS:
                    print(f"[IGNORED] Skipping email from {sender_email}")
                    mark_as_read(token, email_id)
                    continue

                subject         = em.get("subject", "No Subject")
                body            = em.get("bodyPreview", "")
                full_body       = em.get("body", {}).get("content", body)
                has_attachments = em.get("hasAttachments", False)

                print(f"\n[NEW] {sender_name} <{sender_email}>")
                print(f"[SUBJECT] {subject}")

                links = extract_links(full_body)
                if links:
                    print(f"[LINKS] {len(links)} found")

                attachment_data = []
                if has_attachments:
                    attachment_data = get_attachments_content(token, email_id)

                greeting = get_greeting()
                summary  = summarize_with_gemini(
                    sender_name, sender_email, subject, body,
                    attachment_data, links, greeting
                )

                if summary:
                    print(f"[SUMMARY]\n{summary}")

                    # Collect PDF public URLs
                    pdf_urls = []
                    for name, text, raw_bytes in attachment_data:
                        if raw_bytes and name.lower().endswith(".pdf"):
                            print(f"[UPLOAD] Uploading {name}...")
                            pdf_url = upload_pdf_for_whatsapp(raw_bytes, name)
                            if pdf_url:
                                pdf_urls.append(pdf_url)

                    # Send summary + PDF together (first PDF inline, extras as follow-ups)
                    if pdf_urls:
                        send_whatsapp(summary, media_url=pdf_urls[0])
                        for extra in pdf_urls[1:]:
                            send_whatsapp("(Additional attachment)", media_url=extra)
                    else:
                        send_whatsapp(summary)
                else:
                    print("[WARN] No summary returned.")

                mark_as_read(token, email_id)

        except RuntimeError as e:
            # Azure auth failure
            err = str(e)
            print(f"[ERROR] {err}")
            consecutive_errors += 1
            if consecutive_errors == 1:  # alert only first time, not every 30s
                send_alert("Azure Auth Failed", f"{err}\nCheck TENANT_ID, CLIENT_ID, CLIENT_SECRET in .env")

        except requests.exceptions.ConnectionError:
            print("[ERROR] No internet connection.")
            consecutive_errors += 1
            if consecutive_errors == 3:
                send_alert("No Internet", "The email agent lost internet connection for 3 checks in a row.")

        except Exception as e:
            print(f"[ERROR] Unexpected: {e}")
            consecutive_errors += 1
            if consecutive_errors == 1:
                send_alert("Agent Error", f"Unexpected error in email agent:\n{str(e)[:300]}")

        time.sleep(30)


if __name__ == "__main__":
    run()