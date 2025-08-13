from typing import Optional
from langchain_core.tools import tool, BaseTool
from pydantic import BaseModel, Field
from typing import ClassVar
from langchain_community.tools.tavily_search import TavilySearchResults

import os
from dotenv import load_dotenv
load_dotenv()


from tools_utils import (
    insert_booking,
    is_slot_available,
    get_user_slot,
    cancel_slot,
    update_slot,
)

# --- Input Schemas ---
class ReservationInput(BaseModel):
    """Input schema for creating or saving a reservation."""
    name: str
    contact: str
    time: str
    guests: int
    date: str

class SlotInput(BaseModel):
    """Input schema for identifying a time slot."""
    slot: str

class DateInput(BaseModel):
    """Input schema for checking availability on a specific date and time."""
    date: str
    time: Optional[str] = None

class CancelInput(BaseModel):
    """Input schema for cancelling a reservation by ID."""
    slot_id: int

class UpdateBookingInput(BaseModel):
    """Input schema for updating a booking."""
    id: int
    bookingName: str
    contactNumber: str
    bookingDate: str
    bookingTime: str
    noOfPeople: int

class RetrieveInput(BaseModel):
    """Input schema for retrieving bookings using optional name or contact."""
    name: Optional[str] = None
    contact: Optional[str] = None

# --- Tools ---
@tool(args_schema=ReservationInput)
def Create_User_Details(name: str, contact: str, time: str, guests: int, date: str) -> str:
    """Collect booking details before confirmation."""
    return (
        f"📋 Booking details:\n"
        f"👤 Name: {name}\n"
        f"📞 Contact: {contact}\n"
        f"📅 Date: {date}\n"
        f"⏰ Time: {time}\n"
        f"👥 Guests: {guests}\n"
        f"👉 Reply with 'Yes' to confirm or update the details."
    )

@tool(args_schema=ReservationInput)
def Save_Reservation(name: str, contact: str, time: str, guests: int, date: str) -> str:
    """Save a reservation if the selected slot is available, and take time slot of one hour."""
    if is_slot_available(date, time):
        return insert_booking(name, contact, time, guests, date)
    return f"❌ Sorry, booking is full or the slot at {time} on {date} is already booked. Try another time."

@tool(args_schema=DateInput)
def Check_Slot_Availability(date: str, time: Optional[str] = None) -> str:
    """Check whether a time slot is available on a specific date."""
    if time:
        if is_slot_available(date, time):
            return f"✅ Slot available at {time} on {date}."
        return f"❌ Booking full or slot not available on {date, time}."
    return f"❌ Booking full or no available slots on {date}."

@tool(args_schema=RetrieveInput)
def Retrieve_User_Bookings(name: Optional[str] = None, contact: Optional[str] = None) -> str:
    """Retrieve all active or cancelled bookings for a user using name or contact."""
    result = get_user_slot(name=name, contact=contact)
    if isinstance(result, str):
        return result
    if not result:
        return "ℹ️ No active bookings found."
    
    response_lines = ["📖 Your Reservations:"]
    for slot in result:
        status = "✅ Active" if slot.get("isActive", True) else "❌ Cancelled"
        response_lines.append(
            f"- ID #{slot.get('id')} | {slot.get('bookingDate')} at {slot.get('bookingTime')} | Guests: {slot.get('noOfPeople')} | {status}"
        )
    return "\n".join(response_lines)

class Cancel_Reservation(BaseTool):
    """Cancel a reservation by its booking ID."""
    name: ClassVar[str] = "Cancel_Reservation"
    description: ClassVar[str] = "Cancel a reservation by booking ID"
    args_schema: ClassVar[type[BaseModel]] = CancelInput

    def _run(self, slot_id: int) -> str:
        return cancel_slot(slot_id)

class Update_Booking(BaseTool):
    """Update the time and details of an existing reservation."""
    name: ClassVar[str] = "Update_Booking"
    description: ClassVar[str] = "Update a reservation with new details"
    args_schema: ClassVar[type[BaseModel]] = UpdateBookingInput

    def _run(self, **kwargs) -> str:
        return update_slot(kwargs)

# --- Tool Registry ---
all_tools = [
    Create_User_Details,
    Save_Reservation,
    Check_Slot_Availability,
    Retrieve_User_Bookings,
    Cancel_Reservation(),
    Update_Booking(),
]
 