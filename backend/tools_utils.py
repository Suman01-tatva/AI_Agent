from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv
import os
from typing import Optional

# Load environment variables
load_dotenv()
_raw = os.getenv("SLOT_API_URL")
if not _raw:
    raise ValueError("SLOT_API_URL is not set in environment variables.")
SLOT_API_URL = _raw.rstrip("/")


# --- Insert new booking ---
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
        if response.status_code in (200, 201):
            result = response.json()
            booking_id = result.get("id")
            return f"✅ Reservation confirmed! Booking ID: #{booking_id}." if booking_id else "✅ Reservation confirmed!"
        else:
            return f"Error from API: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Error: {str(e)}"

def is_slot_available(date: str, time: Optional[str], guests: int, exclude_id: Optional[int] = None) -> Optional[bool]:
    try:
        if not time:
            return None  # cannot decide without time for capacity model
        params = {"date": date, "time": time, "partySize": guests}
        if exclude_id:
            params["excludeSlotId"] = exclude_id
        resp = requests.get(f"{SLOT_API_URL}/Availability", params=params)
        if resp.status_code == 200:
            data = resp.json()
            return bool(data.get("available", False))
        return None
    except Exception as e:
        print(f"Error checking availability: {e}")
        return None


# --- Fetch user slot(s) by name/contact ---
def get_user_slot(name: str, contact: str):
    try:
        response = requests.get(
            f"{SLOT_API_URL}/GetSlotByContactAndName",
            params={"contactNumber": contact, "name": name},
        )
        if response.status_code == 200:
            return response.json()
        else:
            return {f"Error from Slot API: {response.status_code} - {response.text}"}
    except Exception as e:
        return {f"🔥 Exception while fetching booking: {str(e)}"}

# --- Cancel a slot by ID ---
def cancel_slot(slot_id: int):
    try:
        response = requests.patch(
            f"{SLOT_API_URL}/CancelSlot", params={"slotId": slot_id}
        )
        if response.status_code in (200, 204):
            return f"❌ Reservation ID #{slot_id} has been cancelled successfully."
        else:
            return f"🔥 Failed to cancel: {response.status_code} - {response.text}"
    except Exception as e:
        return f"🔥 Error during cancellation: {str(e)}"

# ---  Update a slot using full slot data ---
def update_slot(slot_data: dict):
    try:
        response = requests.put(f"{SLOT_API_URL}/UpdateSlot", json=slot_data)
        if response.status_code in (200, 204):
            return f"Reservation #{slot_data.get('id')} updated successfully."
        else:
            return f"Failed to update: {response.status_code} - {response.text}"
    except Exception as e:
        return f"🔥 Error during update: {str(e)}"