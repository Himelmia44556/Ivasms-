import requests
import re
import json
import time
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os
from telegram import Bot
import asyncio

# Load environment variables
load_dotenv()

IVASMS_EMAIL = os.getenv("IVASMS_EMAIL")
IVASMS_PASSWORD = os.getenv("IVASMS_PASSWORD")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Headers
BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "*/*",
    "Connection": "keep-alive"
}

# ---------------- TELEGRAM ---------------- #
async def send_to_telegram(sms):
    bot = Bot(token=BOT_TOKEN)
    message = (
        f"📩 New SMS\n\n"
        f"🕒 {sms['timestamp']}\n"
        f"📞 +{sms['number']}\n\n"
        f"💬 {sms['message']}"
    )
    try:
        await bot.send_message(chat_id=CHAT_ID, text=message)
        print("Sent:", sms["number"])
    except Exception as e:
        print("Telegram Error:", e)

# ---------------- LOGIN ---------------- #
def payload_1(session):
    r = session.get("https://www.ivasms.com/login", headers=BASE_HEADERS)
    token = re.search(r'name="_token" value="([^"]+)"', r.text)
    if not token:
        raise Exception("Token not found")
    return token.group(1)

def payload_2(session, token):
    data = {
        "_token": token,
        "email": IVASMS_EMAIL,
        "password": IVASMS_PASSWORD
    }
    r = session.post("https://www.ivasms.com/login", data=data, headers=BASE_HEADERS)
    if "/login" in r.url:
        raise Exception("Login failed")

def payload_3(session):
    r = session.get("https://www.ivasms.com/portal/sms/received", headers=BASE_HEADERS)
    token = re.search(r'csrf-token" content="([^"]+)"', r.text)
    if not token:
        raise Exception("CSRF not found")
    return token.group(1)

# ---------------- FETCH ---------------- #
def payload_4(session, csrf, from_date, to_date):
    data = {
        "_token": csrf,
        "from": from_date,
        "to": to_date
    }
    return session.post(
        "https://www.ivasms.com/portal/sms/received/getsms",
        data=data,
        headers=BASE_HEADERS
    )

def payload_5(session, csrf, to_date, range_name):
    data = {
        "_token": csrf,
        "start": "",
        "end": to_date,
        "range": range_name
    }
    return session.post(
        "https://www.ivasms.com/portal/sms/received/getsms/number",
        data=data,
        headers=BASE_HEADERS
    )

def payload_6(session, csrf, to_date, number, range_name):
    data = {
        "_token": csrf,
        "start": "",
        "end": to_date,
        "Number": number,
        "Range": range_name
    }
    return session.post(
        "https://www.ivasms.com/portal/sms/received/getsms/number/sms",
        data=data,
        headers=BASE_HEADERS
    )

# ---------------- PARSE ---------------- #
def parse_ranges(html):
    soup = BeautifulSoup(html, "html.parser")
    data = []

    cards = soup.find_all("div", class_="card card-body mb-1 pointer")
    for c in cards:
        cols = c.find_all("div")
        if len(cols) < 2:
            continue

        name = cols[0].text.strip()
        count = int(cols[1].text.strip() or 0)

        data.append({
            "range_name": name,
            "count": count
        })
    return data

def parse_numbers(html):
    soup = BeautifulSoup(html, "html.parser")
    numbers = []

    divs = soup.find_all("div", class_="card card-body")
    for d in divs:
        onclick = d.get("onclick", "")
        match = re.search(r"'([^']+)'", onclick)
        if match:
            numbers.append(match.group(1))
    return numbers

def parse_message(html):
    soup = BeautifulSoup(html, "html.parser")
    p = soup.find("p")
    return p.text.strip() if p else "No message"

# ---------------- STORAGE ---------------- #
FILE = "data.json"

def load_data():
    if os.path.exists(FILE):
        return json.load(open(FILE))
    return {}

def save_data(data):
    json.dump(data, open(FILE, "w"), indent=2)

# ---------------- MAIN ---------------- #
async def main():
    while True:
        try:
            with requests.Session() as session:
                token = payload_1(session)
                payload_2(session, token)
                csrf = payload_3(session)

                today = datetime.now()
                from_date = today.strftime("%m/%d/%Y")
                to_date = (today + timedelta(days=1)).strftime("%m/%d/%Y")

                old = load_data()

                res = payload_4(session, csrf, from_date, to_date)
                ranges = parse_ranges(res.text)

                for r in ranges:
                    name = r["range_name"]
                    count = r["count"]

                    if name not in old or count > old[name]:
                        print("New SMS in:", name)

                        res2 = payload_5(session, csrf, to_date, name)
                        numbers = parse_numbers(res2.text)

                        for num in numbers[-3:]:  # last few only
                            res3 = payload_6(session, csrf, to_date, num, name)
                            msg = parse_message(res3.text)

                            sms = {
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "number": num,
                                "message": msg
                            }

                            await send_to_telegram(sms)

                    old[name] = count

                save_data(old)

            await asyncio.sleep(5)

        except Exception as e:
            print("Error:", e)
            await asyncio.sleep(20)

# ---------------- RUN ---------------- #
if __name__ == "__main__":
    asyncio.run(main())
