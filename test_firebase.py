import firebase_admin
from firebase_admin import credentials, db

# Step 1: Load JSON key
cred = credentials.Certificate("infield-booking-watsapp-firebase-adminsdk-fbsvc-eb879e5496.json")

# Step 2: Initialize Firebase
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://infield-booking-watsapp-default-rtdb.asia-southeast1.firebasedatabase.app/'
})

# Step 3: Read data
ref = db.reference("slots/2026-04-01")
data = ref.get()


ref = db.reference("slots/2026-04-01/7-8 PM")

ref.update({
    "status": "cancelled",
    "user": "Akash M"
})

print("Slot booked!")

ref = db.reference("slots/2026-04-01")
data = ref.get()

print("Updated Slots data:", data)
