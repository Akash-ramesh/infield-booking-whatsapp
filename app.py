from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import firebase_admin
from firebase_admin import credentials, db
import os
import json
from datetime import datetime

app = Flask(__name__)

# ✅ Firebase setup (using ENV variable)
firebase_json = json.loads(os.environ["FIREBASE_CREDENTIALS"])
cred = credentials.Certificate(firebase_json)

firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://infield-booking-watsapp-default-rtdb.asia-southeast1.firebasedatabase.app/'
})

# ✅ Generate slots from 6 AM to 12 AM
def generate_slots():
    slots = {}
    for hour in range(6, 24):
        start = f"{hour % 12 or 12} {'AM' if hour < 12 else 'PM'}"
        end = f"{(hour+1) % 12 or 12} {'AM' if hour+1 < 12 else 'PM'}"
        slots[f"{start}-{end}"] = {"status": "available"}
    return slots


@app.route("/whatsapp", methods=['POST'])
def whatsapp_reply():
    incoming_msg = request.form.get('Body').strip().lower()

    resp = MessagingResponse()
    msg = resp.message()

    today = datetime.now().strftime("%Y-%m-%d")

    # =====================
    # STEP 1: GREETING
    # =====================
    if incoming_msg in ["hi", "hello"]:
        reply = (
            "Choose option:\n"
            "1. Show today's available slots\n"
            "2. Book for another date"
        )
        msg.body(reply)
        return str(resp)

    # =====================
    # STEP 2: TODAY FLOW
    # =====================
    if incoming_msg == "1":
        ref = db.reference(f"slots/{today}")
        data = ref.get()

        # Auto create slots if not exist
        if not data:
            data = generate_slots()
            ref.set(data)

        available_slots = [
            slot for slot, info in data.items()
            if info["status"] == "available"
        ]

        if not available_slots:
            msg.body("❌ No slots available for today")
            return str(resp)

        reply = "Available slots:\n"
        for i, slot in enumerate(available_slots, 1):
            reply += f"{i}. {slot}\n"

        reply += "\nReply with slot number to book"

        # Store available slots temporarily
        db.reference("temp/user_slots").set(available_slots)

        msg.body(reply)
        return str(resp)

    # =====================
    # STEP 3: OTHER DATE
    # =====================
    if incoming_msg == "2":
        msg.body("Enter date in format YYYY-MM-DD (e.g. 2026-04-05)")
        return str(resp)

    # If user sends date
    if "-" in incoming_msg:
        selected_date = incoming_msg

        ref = db.reference(f"slots/{selected_date}")
        data = ref.get()

        if not data:
            data = generate_slots()
            ref.set(data)

        available_slots = [
            slot for slot, info in data.items()
            if info["status"] == "available"
        ]

        if not available_slots:
            msg.body("❌ No slots available for this date")
            return str(resp)

        reply = f"Available slots for {selected_date}:\n"
        for i, slot in enumerate(available_slots, 1):
            reply += f"{i}. {slot}\n"

        reply += "\nReply with slot number to book"

        # Save temp slots + date
        db.reference("temp/user_slots").set(available_slots)
        db.reference("temp/date").set(selected_date)

        msg.body(reply)
        return str(resp)

    # =====================
    # STEP 4: BOOK SLOT
    # =====================
    if incoming_msg.isdigit():
        index = int(incoming_msg) - 1

        available_slots = db.reference("temp/user_slots").get()
        selected_date = db.reference("temp/date").get() or today

        if not available_slots or index >= len(available_slots):
            msg.body("❌ Invalid selection")
            return str(resp)

        selected_slot = available_slots[index]

        slot_ref = db.reference(f"slots/{selected_date}/{selected_slot}")

        # Double booking protection
        current_data = slot_ref.get()
        if current_data["status"] == "booked":
            msg.body("❌ Slot already booked")
            return str(resp)

        slot_ref.update({
            "status": "booked",
            "user": request.form.get('From')  # store phone number
        })

        msg.body(f"✅ Slot {selected_slot} booked for {selected_date}")
        return str(resp)

    # =====================
    # DEFAULT
    # =====================
    msg.body("Send 'Hi' to start")
    return str(resp)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
