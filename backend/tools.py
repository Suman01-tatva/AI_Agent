from typing import Optional
from langchain_core.tools import tool, BaseTool
from pydantic import BaseModel, Field
from datetime import date
from dotenv import load_dotenv

from tools_utils import (
    insert_booking,
    is_slot_available,
    get_user_slot,
    cancel_slot,
    update_slot,
)

load_dotenv()
today_str = date.today().isoformat()

# --- Input Schemas ---
class ReservationInput(BaseModel):
    """Input schema for creating or saving a reservation."""
    name: str = Field(..., description="Name of the user, e.g., John, Suman")
    contact: str = Field(..., min_length=10, max_length=13,description="Contact number of the user, e.g., +91-1234567890")
    time: str = Field(..., description="Time in HH:MM:SS format, use 'retriever_tool' for opening hours must be between restaurant opening hours")
    guests: int = Field(..., gt=0, description="Number of people, > 0")
    date: str = Field(..., description=f"Date in YYYY-MM-DD format, > {today_str}")

class CancelInput(BaseModel):
    """Input schema for cancelling a reservation by ID."""
    slot_id: int = Field(...,gt=0, description="ID of the booking to cancel, must be greater than 0")

class UpdateBookingInput(BaseModel):
    """Input schema for updating a booking."""
    id: int
    bookingName: str = Field(..., description="Name of the user, e.g., John, Suman")
    contactNumber: str = Field(..., min_length=10, max_length=13,description="Contact number of the user, e.g., +91-1234567890")
    bookingDate: str = Field(..., description=f"Date in YYYY-MM-DD format, > {today_str}")
    bookingTime: str = Field(..., description="Time in HH:MM:SS format, must be between restaurant opening hours")
    noOfPeople: int = Field(..., gt=0, description="Number of people, > 0")

class RetrieveInput(BaseModel):
    """Input schema for retrieving bookings using optional name or contact."""
    name: Optional[str] = Field(..., description="Name of the user, e.g., John, Suman")
    contact: Optional[str] = Field(..., min_length=10, max_length=13,description="Contact number of the user, e.g., +91-1234567890")

# --- Tools ---  

@tool(args_schema=ReservationInput)
def Save_Reservation(name: str, contact: str, time: str, guests: int, date: str) -> str:
    """Save a reservation if the selected slot is available, and take time slot of one hour."""
    slot_status = is_slot_available(date, time)
    if slot_status is None:
        return "ℹ️ Unable to check availability at the moment. Please try again later."
    elif slot_status:
        return insert_booking(name, contact, time, guests, date)
    return f"Sorry, booking is full or the slot at {time} on {date} is already booked. Try another time."

@tool(args_schema=RetrieveInput)
def Retrieve_User_Bookings(name: Optional[str] = None, contact: Optional[str] = None) -> str:
    """Retrieve all active or cancelled bookings for a user using name or contact."""
    result = get_user_slot(name=name, contact=contact)
    if isinstance(result, str):
        return result
    if not result:
        return "No active bookings found."
    
    response_lines = ["Your Reservations:"]
    for slot in result:
        status = "Active" if slot.get("isActive", True) else "Cancelled"
        response_lines.append(
            f"- ID #{slot.get('id')} | {slot.get('bookingDate')} at {slot.get('bookingTime')} | Guests: {slot.get('noOfPeople')} | {status}"
        )
    return "\n".join(response_lines)

@tool(args_schema=CancelInput)
def Cancel_Reservation(slot_id: int):
    """Cancels a slot by ID."""
    return cancel_slot(slot_id)
    
class Update_Booking(BaseTool):
    """Update the time and details of an existing reservation."""
    name: str = "Update_Booking"
    description: str = "Update a reservation with new details"
    args_schema: type[BaseModel] = UpdateBookingInput

    def _run(self, **kwargs) -> str:
        return update_slot(kwargs)

# --- Tool Registry ---
all_tools = [
    Save_Reservation,
    Retrieve_User_Bookings,
    Cancel_Reservation,
    Update_Booking(),
]
 