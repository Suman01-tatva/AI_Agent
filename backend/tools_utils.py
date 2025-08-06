from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv
import os
from typing import Optional

# Load environment variables
load_dotenv()
SLOT_API_URL = os.getenv("SLOT_API_URL")
if not SLOT_API_URL:
    raise ValueError("SLOT_API_URL is not set in environment variables.")

# --- ⏱️ Generate time slots ---
def generate_time_slots(start="10:00", end="22:00", interval_minutes=30):
    slots = []
    current = datetime.strptime(start, "%H:%M")
    end_time = datetime.strptime(end, "%H:%M")
    while current <= end_time:
        slots.append(current.strftime("%H:%M"))
        current += timedelta(minutes=interval_minutes)
    return slots

time_slots = generate_time_slots()

# --- 📥 Insert new booking ---
def insert_booking(name: str, contact: str, time: str, guests: int, date: str):
    try:
        payload = {
            "bookingName": name,
            "bookingDate": date,
            "bookingTime": time,
            "noOfPeople": guests,
            "contactNumber": contact,
        }
        response = requests.post(SLOT_API_URL, json=payload)
        if response.status_code == 200:
            result = response.json()
            return f"✅ Your reservation is confirmed! Booking ID: #{result['id']}."
        else:
            return f"🔥 Error from API: {response.status_code} - {response.text}"
    except Exception as e:
        return f"🔥 Error: {str(e)}"

# --- ✅ Check if slot is available ---
def is_slot_available(date: str, time: Optional[str] = None) -> bool:
    try:
        params = {"date": date}
        if time:
            params["time"] = time

        response = requests.get(SLOT_API_URL, params=params)
        if response.status_code != 200:
            print(f"API request failed with status {response.status_code}")
            return False

        slots = response.json()
        if time:
            booked_times = [
                slot["bookingTime"] for slot in slots if slot.get("isActive", True)
            ]
            return time not in booked_times
        else:
            return len(slots) > 0

    except Exception as e:
        print(f"Error checking slot availability: {str(e)}")
        return False

# --- ⏭️ Get next available time slot ---
def get_next_available_slot(date: str, current_time: str):
    try:
        response = requests.get(SLOT_API_URL, params={"date": date})
        if response.status_code != 200:
            return None
        booked_slots = response.json()
        booked_times = {
            slot["bookingTime"] for slot in booked_slots if slot.get("isActive", True)
        }
        start_index = (
            time_slots.index(current_time) if current_time in time_slots else -1
        )
        for next_time in time_slots[start_index + 1:]:
            if next_time not in booked_times:
                return next_time
        return None
    except Exception:
        return None

# --- 🔍 Fetch user slot(s) by name/contact ---
def get_user_slot(name: str, contact: str):
    try:
        response = requests.get(
            f"{SLOT_API_URL}/GetSlotByContactAndName",
            params={"contactNumber": contact, "name": name},
        )
        if response.status_code == 200:
            return response.json()
        else:
            return f"🔥 Error from Slot API: {response.status_code} - {response.text}"
    except Exception as e:
        return f"🔥 Exception while fetching booking: {str(e)}"

# --- ❌ Cancel a slot by ID ---
def cancel_slot(slot_id: int):
    try:
        response = requests.patch(
            f"{SLOT_API_URL}/CancelSlot", params={"slotId": slot_id}
        )
        if response.status_code == 200:
            return f"❌ Reservation ID #{slot_id} has been cancelled successfully."
        else:
            return f"🔥 Failed to cancel: {response.status_code} - {response.text}"
    except Exception as e:
        return f"🔥 Error during cancellation: {str(e)}"

# --- ✏️ Update a slot using full slot data ---
def update_slot(slot_data: dict):
    try:
        response = requests.put(f"{SLOT_API_URL}/UpdateSlot", json=slot_data)
        if response.status_code == 200:
            return f"✏️ Reservation #{slot_data.get('id')} updated successfully."
        else:
            return f"🔥 Failed to update: {response.status_code} - {response.text}"
    except Exception as e:
        return f"🔥 Error during update: {str(e)}"