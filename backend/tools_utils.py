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
        if response.status_code == 200:
            result = response.json()
            return f"Your reservation is confirmed! Booking ID: #{result['id']}."
        else:
            return f"Error from API: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Error: {str(e)}"

# --- Check if slot is available ---
def is_slot_available(date: str, time: Optional[str] = None) -> bool:
    try:
        params = {"date": date}
        if time:
            params["time"] = time

        response = requests.get(SLOT_API_URL, params=params)
        if response.status_code != 200:
            print(f"API request failed with status {response.status_code}")
            return False
        elif response.status_code == 500:
            return None
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
            return f"🔥 Error from Slot API: {response.status_code} - {response.text}"
    except Exception as e:
        return f"🔥 Exception while fetching booking: {str(e)}"

# --- Cancel a slot by ID ---
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

# ---  Update a slot using full slot data ---
def update_slot(slot_data: dict):
    try:
        response = requests.put(f"{SLOT_API_URL}/UpdateSlot", json=slot_data)
        if response.status_code == 200:
            return f"Reservation #{slot_data.get('id')} updated successfully."
        else:
            return f"Failed to update: {response.status_code} - {response.text}"
    except Exception as e:
        return f"🔥 Error during update: {str(e)}"