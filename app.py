from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import firebase_admin
from firebase_admin import credentials, db
import os
import json
from datetime import datetime

app = Flask(__name__)

# Firebase setup
firebase_json = json.loads(os.environ["FIREBASE_CREDENTIALS"])
cred = credentials.Certificate(firebase_json)

firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://infield-booking-watsapp-default-rtdb.asia-southeast1.firebasedatabase.app/'
})


# Generate slots
def generate_slots():
    slots = {}
    for hour in range(6, 24):
        start = f"{hour % 12 or 12} {'AM' if hour < 12 else 'PM'}"
        end = f"{(hour+1) % 12 or 12} {'AM' if hour+1 < 12 else 'PM'}"
        slots[f"{start}-{end}"] = {"status": "available"}
    return slots


# Invalid handler
def handle_invalid(temp_ref, temp_data, msg):
    attempts = temp_data.get("invalid_attempts", 0) + 1

    if attempts >= 3:
        temp_ref.delete()
        msg.body(
            "❌ Too many invalid attempts.\n\n"
            "Restarting...\n\n"
            "Send 'Hi' to begin."
        )
        return True

    temp_ref.update({"invalid_attempts": attempts})
    msg.body(
        f"⚠️ Invalid choice ({attempts}/3)\n"
        "Try again.\n\n"
        "Type B → Back\n"
        "Type 0 → Exit"
    )
    return True


# Main Menu helper
def main_menu():
    return (
        "Main Menu:\n"
        "1. Book for today\n"
        "2. Book for another date\n"
        "3. Cancel booking\n"
        "0. Exit"
    )


@app.route("/whatsapp", methods=['POST'])
def whatsapp_reply():
    incoming_msg = request.form.get('Body').strip()
    user_phone = request.form.get('From')

    resp = MessagingResponse()
    msg = resp.message()

    today = datetime.now().strftime("%Y-%m-%d")

    temp_ref = db.reference(f"temp/{user_phone}")
    temp_data = temp_ref.get() or {}

    # EXIT
    if incoming_msg == "0":
        temp_ref.delete()
        msg.body("✅ Session ended. Send 'Hi' to start again.")
        return str(resp)

    # BACK
    if incoming_msg.lower() == "b":
        temp_ref.delete()
        msg.body(main_menu())
        return str(resp)

    # START
    if incoming_msg.lower() in ["hi", "hello"]:
        msg.body("Welcome to Infield Turf ⚽\n\n" + main_menu())
        return str(resp)

    # =====================
    # OPTION 1: TODAY
    # =====================
    if incoming_msg == "1":
        ref = db.reference(f"slots/{today}")
        data = ref.get()

        if not data:
            data = generate_slots()
            ref.set(data)

        available = sorted([s for s, i in data.items() if i["status"] == "available"])

        if not available:
            temp_ref.delete()
            msg.body(
                "❌ No slots available today\n\n"
                "Returning to main menu...\n\n" + main_menu()
            )
            return str(resp)

        temp_ref.set({
            "step": "select_slot",
            "slots": available,
            "date": today
        })

        reply = "Available slots:\n"
        for i, slot in enumerate(available, 1):
            reply += f"{i}. {slot}\n"

        reply += "\nReply with slot number"
        reply += "\nType B → Back"
        reply += "\nType 0 → Exit"

        msg.body(reply)
        return str(resp)

    # =====================
    # OPTION 2: OTHER DATE
    # =====================
    if incoming_msg == "2":
        temp_ref.set({"step": "enter_date"})
        msg.body("Enter date (YYYY-MM-DD)\nType B → Back\nType 0 → Exit")
        return str(resp)

    if temp_data.get("step") == "enter_date":
        selected_date = incoming_msg

        ref = db.reference(f"slots/{selected_date}")
        data = ref.get()

        if not data:
            data = generate_slots()
            ref.set(data)

        available = sorted([s for s, i in data.items() if i["status"] == "available"])

        if not available:
            temp_ref.delete()
            msg.body(
                "❌ No slots available\n\n"
                "Returning to main menu...\n\n" + main_menu()
            )
            return str(resp)

        temp_ref.set({
            "step": "select_slot",
            "slots": available,
            "date": selected_date
        })

        reply = f"Slots for {selected_date}:\n"
        for i, slot in enumerate(available, 1):
            reply += f"{i}. {slot}\n"

        reply += "\nReply with slot number"
        reply += "\nType B → Back"
        reply += "\nType 0 → Exit"

        msg.body(reply)
        return str(resp)

    # =====================
    # SLOT SELECT → ASK NAME
    # =====================
    if temp_data.get("step") == "select_slot":
        if not incoming_msg.isdigit():
            return str(resp) if handle_invalid(temp_ref, temp_data, msg) else None

        index = int(incoming_msg) - 1
        slots = temp_data["slots"]

        if index >= len(slots):
            return str(resp) if handle_invalid(temp_ref, temp_data, msg) else None

        selected_slot = slots[index]

        temp_ref.update({
            "step": "ask_name",
            "selected_slot": selected_slot
        })

        msg.body(f"Selected: {selected_slot}\n\nEnter your name:\nType B → Back")
        return str(resp)

    # =====================
    # NAME → BOOK
    # =====================
    if temp_data.get("step") == "ask_name":
        name = incoming_msg
        slot = temp_data["selected_slot"]
        date = temp_data["date"]

        slot_ref = db.reference(f"slots/{date}/{slot}")
        current = slot_ref.get()

        if current["status"] == "booked":
            msg.body("❌ Slot already booked\nType B → Back")
            return str(resp)

        slot_ref.update({
            "status": "booked",
            "user": user_phone,
            "name": name
        })

        temp_ref.delete()

        msg.body(
            f"✅ Booked {slot} on {date}\n\n"
            f"Thank you {name} 🙌\n\n" +
            main_menu()
        )
        return str(resp)

    # =====================
    # CANCEL BOOKING
    # =====================
    if incoming_msg == "3":
        all_slots = db.reference("slots").get()
        user_bookings = []

        for date, slots in (all_slots or {}).items():
            for slot, info in slots.items():
                if info.get("user") == user_phone:
                    user_bookings.append((date, slot))

        if not user_bookings:
            temp_ref.delete()
            msg.body(
                "❌ No bookings found\n\n"
                "Returning to main menu...\n\n" + main_menu()
            )
            return str(resp)

        temp_ref.set({
            "step": "cancel",
            "bookings": user_bookings
        })

        reply = "Your bookings:\n"
        for i, (d, s) in enumerate(user_bookings, 1):
            reply += f"{i}. {s} on {d}\n"

        reply += "\nReply with number to cancel"
        reply += "\nType B → Back"
        reply += "\nType 0 → Exit"

        msg.body(reply)
        return str(resp)

    # CANCEL SELECT
    if temp_data.get("step") == "cancel":
        if not incoming_msg.isdigit():
            return str(resp) if handle_invalid(temp_ref, temp_data, msg) else None

        index = int(incoming_msg) - 1
        bookings = temp_data["bookings"]

        if index >= len(bookings):
            return str(resp) if handle_invalid(temp_ref, temp_data, msg) else None

        date, slot = bookings[index]

        db.reference(f"slots/{date}/{slot}").update({
            "status": "available",
            "user": "",
            "name": ""
        })

        temp_ref.delete()

        msg.body(
            f"❌ Cancelled {slot} on {date}\n\n"
            "Returning to main menu...\n\n" + main_menu()
        )
        return str(resp)

    msg.body("Send 'Hi' to start\nType 0 → Exit")
    return str(resp)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
