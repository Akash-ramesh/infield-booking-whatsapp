from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import firebase_admin
from firebase_admin import credentials, db
from datetime import datetime

app = Flask(__name__)

# ✅ Firebase setup (your values)
cred = credentials.Certificate("infield-booking-watsapp-firebase-adminsdk-fbsvc-eb879e5496.json")

firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://infield-booking-watsapp-default-rtdb.asia-southeast1.firebasedatabase.app/'
})

user_states = {}

# 🔥 Generate slots (6 AM → 12 AM)
def generate_slots():
    slots = {}

    for hour in range(6, 24):
        start = hour
        end = hour + 1

        def format_time(h):
            suffix = "AM" if h < 12 else "PM"
            h = h % 12
            if h == 0:
                h = 12
            return f"{h} {suffix}"

        slot_name = f"{format_time(start)} - {format_time(end)}"
        slots[slot_name] = {"status": "available"}

    return slots


# 🔥 Create slots for date
def create_slots_for_date(date):
    ref = db.reference(f"slots/{date}")
    if ref.get():
        return
    ref.set(generate_slots())


# 🔥 Filter past slots (today only)
def filter_past_slots(slots):
    current_hour = datetime.now().hour
    filtered = []

    for slot in slots:
        start = slot.split(" - ")[0]
        hour = int(start.split()[0])
        suffix = start.split()[1]

        if suffix == "PM" and hour != 12:
            hour += 12
        if suffix == "AM" and hour == 12:
            hour = 0

        if hour > current_hour:
            filtered.append(slot)

    return filtered


@app.route("/whatsapp", methods=['POST'])
def whatsapp_reply():
    incoming_msg = request.form.get('Body').strip()
    user = request.form.get('From')

    resp = MessagingResponse()
    msg = resp.message()

    # ✅ STEP 1: Start
    if incoming_msg.lower() == "hi":
        user_states[user] = {"step": "menu"}
        msg.body(
            "Choose option:\n"
            "1. Show today's available slots\n"
            "2. Book for another date"
        )
        return str(resp)

    # ✅ STEP 2: Menu
    if user in user_states and user_states[user]["step"] == "menu":

        # OPTION 1: Today
        if incoming_msg == "1":
            date = datetime.now().strftime("%Y-%m-%d")

            create_slots_for_date(date)
            ref = db.reference(f"slots/{date}")
            data = ref.get()

            available_slots = [s for s, v in data.items() if v["status"] == "available"]
            available_slots = filter_past_slots(available_slots)

            if not available_slots:
                msg.body("❌ No slots available for today")
                return str(resp)

            user_states[user] = {"step": "slot", "date": date, "slots": available_slots}

            reply = f"Available slots for today ({date}):\n"
            for i, slot in enumerate(available_slots, 1):
                reply += f"{i}. {slot}\n"

            reply += "\nReply with slot number"
            msg.body(reply)
            return str(resp)

        # OPTION 2: Another date
        elif incoming_msg == "2":
            user_states[user] = {"step": "enter_date"}
            msg.body("Enter date (YYYY-MM-DD):")
            return str(resp)

        else:
            msg.body("Please choose 1 or 2")
            return str(resp)

    # ✅ STEP 3: Custom date
    if user in user_states and user_states[user]["step"] == "enter_date":
        date = incoming_msg

        create_slots_for_date(date)
        ref = db.reference(f"slots/{date}")
        data = ref.get()

        available_slots = [s for s, v in data.items() if v["status"] == "available"]

        if not available_slots:
            msg.body("❌ No slots available for this date")
            return str(resp)

        user_states[user] = {"step": "slot", "date": date, "slots": available_slots}

        reply = f"Available slots for {date}:\n"
        for i, slot in enumerate(available_slots, 1):
            reply += f"{i}. {slot}\n"

        reply += "\nReply with slot number"
        msg.body(reply)
        return str(resp)

    # ✅ STEP 4: Booking
    if user in user_states and user_states[user]["step"] == "slot":
        try:
            index = int(incoming_msg) - 1
            selected = user_states[user]["slots"][index]
            date = user_states[user]["date"]

            slot_ref = db.reference(f"slots/{date}/{selected}")
            current = slot_ref.get()

            if current["status"] == "booked":
                msg.body("❌ Slot already booked. Try another.")
                return str(resp)

            slot_ref.update({
                "status": "booked",
                "user": user
            })

            msg.body(f"✅ Slot {selected} booked on {date}")

        except:
            msg.body("Invalid selection")

        return str(resp)

    msg.body("Send 'Hi' to start")
    return str(resp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
