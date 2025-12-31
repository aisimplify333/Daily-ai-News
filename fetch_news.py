import imaplib
import email
from email.header import decode_header
from bs4 import BeautifulSoup
import datetime
import os

# --- CONFIGURATION ---
EMAIL_USER = "aisimplifynewsfeed@gmail.com" 
EMAIL_PASS = os.environ.get("EMAIL_APP_PASSWORD") 
IMAP_SERVER = "imap.gmail.com"

def clean_subject(subject):
    decoded_list = decode_header(subject)
    full_subject = ""
    for decoded_part, encoding in decoded_list:
        if isinstance(decoded_part, bytes):
            if encoding:
                full_subject += decoded_part.decode(encoding)
            else:
                full_subject += decoded_part.decode('utf-8', errors='ignore')
        else:
            full_subject += str(decoded_part)
    return full_subject

def extract_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            if "attachment" not in content_disposition:
                if content_type == "text/plain":
                    return part.get_payload(decode=True).decode()
                elif content_type == "text/html":
                    html_content = part.get_payload(decode=True).decode()
                    soup = BeautifulSoup(html_content, "html.parser")
                    return soup.get_text()
    else:
        content_type = msg.get_content_type()
        if content_type == "text/plain":
            return msg.get_payload(decode=True).decode()
        elif content_type == "text/html":
            html_content = msg.get_payload(decode=True).decode()
            soup = BeautifulSoup(html_content, "html.parser")
            return soup.get_text()
    return ""

def get_todays_newsletters():
    print(" >> 📧 CONNECTING TO NEWSWIRE...")
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")

        # Search for emails from TODAY
        date_str = datetime.date.today().strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'(SINCE "{date_str}")')
        
        email_ids = messages[0].split()
        print(f"    ...Found {len(email_ids)} emails from today.")
        
        intel_digest = ""
        
        # Process last 3 emails (Top priority)
        for i in reversed(email_ids[-3:]):
            res, msg_data = mail.fetch(i, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    subject = clean_subject(msg["Subject"])
                    print(f"    ...Processing: {subject}")
                    body = extract_body(msg)
                    
                    # Clean up the body text (remove huge whitespace)
                    clean_body = " ".join(body.split())[:3000] 
                    intel_digest += f"\nSOURCE: {subject}\nCONTENT: {clean_body}\n{'-'*20}\n"
        
        mail.close()
        mail.logout()
        
        if not intel_digest:
            print("    ⚠️ NO EMAILS FOUND. USING SIMULATION DATA.")
            return None
            
        return intel_digest

    except Exception as e:
        print(f"    ❌ EMAIL ERROR: {e}")
        return None

if __name__ == "__main__":
    print(get_todays_newsletters())
