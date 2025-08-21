import requests
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()
SLOT_API_URL = os.getenv("SLOT_API_URL")
if not SLOT_API_URL:
    raise ValueError("SLOT_API_URL is not set in environment variables.")

# --- Check slot and save slot ---
def check_and_save_slot(name: str, contact: str, time: str, guests: int, date: str) -> str:
    try:
        # Step 1: Check availability
        availability_url = f"{SLOT_API_URL}/Availability"
        params = {"date": date, "time": time, "partySize": guests}
        response = requests.get(availability_url, params=params)

        if response.status_code != 200:
            return f"Error checking availability: {response.status_code} - {response.text}"

        availability = response.json()
        if not availability["available"]:
            return (
                f"❌ Sorry, we cannot accommodate {guests} people at {time} on {date}. "
                f"Remaining capacity: {availability['remainingCapacity']} out of {availability['capacity']}."
            )

        # Step 2: Book the slot
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
            return f"Error saving booking: {response.status_code} - {response.text}"

    except Exception as e:
        return f"🔥 Exception while booking: {str(e)}"

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
def cancel_slot(slot_id: int) -> str:
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
def update_slot(slot_data: dict) -> str:
    try:
        response = requests.put(f"{SLOT_API_URL}/UpdateSlot", json=slot_data)
        if response.status_code in (200, 204):
            return f"Reservation #{slot_data.get('id')} updated successfully."
        else:
            return f"Failed to update: {response.status_code} - {response.text}"
    except Exception as e:
        return f"🔥 Error during update: {str(e)}"