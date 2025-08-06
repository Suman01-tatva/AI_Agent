from typing import Optional
from langchain_core.tools import tool, BaseTool
from pydantic import BaseModel, Field

from tools_utils import (
    insert_booking,
    is_slot_available,
    get_next_available_slot,
    get_user_slot,
    cancel_slot,
    update_slot,
    time_slots,
)
from typing import ClassVar

# --- Input Schemas ---

class ReservationInput(BaseModel):
    name: str = Field(..., description="Customer name")
    contact: str = Field(..., description="Customer contact number")
    time: str = Field(..., description="Booking time in HH:MM")
    guests: int = Field(..., description="Number of guests")
    date: str = Field(..., description="Booking date in YYYY-MM-DD")

class SlotInput(BaseModel):
    slot: str = Field(..., description="Suggested time slot in HH:MM format")

class DateInput(BaseModel):
    date: str = Field(..., description="Date to check for available slots")
    time: Optional[str] = Field(None, description="Specific time to check availability in formate like(10 PM,11AM), if any")

class CancelInput(BaseModel):
    slot_id: int = Field(..., description="ID of the booking to cancel")

class UpdateBookingInput(BaseModel):
    id: int
    bookingName: str
    contactNumber: str
    bookingDate: str
    bookingTime: str
    noOfPeople: int

class RetrieveInput(BaseModel):
    name: Optional[str] = Field(None, description="Customer name")
    contact: Optional[str] = Field(None, description="Customer contact number")

# --- Tools ---

@tool(args_schema=ReservationInput)
def Save_Reservation(name: str, contact: str, time: str, guests: int, date: str) -> str:
    """Checks availability and saves reservation if possible, or suggests next available slot."""
    if is_slot_available(date, time):
        return insert_booking(name, contact, time, guests, date)
    next_slot = get_next_available_slot(date, time)
    return (
        f"❌ {time} on {date} is full.\n👉 Next available: {next_slot}"
        if next_slot else f"❌ No slots available on {date}."
    )

@tool(args_schema=DateInput)
def Check_Slot_Availability(date: str , time: Optional[str]) -> str:
    """Returns available time slots for a given date. If a specific time is provided, checks availability. """
    if time:
        if not is_slot_available(date, time):
            return f"✅ The table is available on {date} at {time}."
        else:
            return f"❌ The table is already occupied on {date} at {time}."

    available = [t for t in time_slots if is_slot_available(date, t)]
    if available:
        return f"✅ Available time slots on {date}: {available}"
    else:
        return f"❌ No slots available on {date}."

@tool(args_schema=RetrieveInput)
def Retrieve_User_Bookings(name: Optional[str] = None, contact: Optional[str] = None) -> str:
    """Retrieves current reservation(s) for a given user by name or contact number."""
    return get_user_slot(name=name, contact=contact)

class Cancel_Reservation(BaseTool):
    name: ClassVar[str] = "Cancel_Reservation"
    description: ClassVar[str] = "Cancels a user's booking based on slot ID"
    args_schema: ClassVar[type[BaseModel]] = CancelInput

    def _run(self, slot_id: int) -> str:
        return cancel_slot(slot_id)

class Update_Booking_Time(BaseTool):
    name: ClassVar[str] = "Update_Booking_Time"
    description: ClassVar[str] = "Updates a user's booking time using full slot info"
    args_schema: ClassVar[type[BaseModel]] = UpdateBookingInput

    def _run(self, **kwargs) -> str:
        return update_slot(kwargs)

# --- Tool Registry ---
all_tools = [
    # Create_User_Details,
    Save_Reservation,
    Check_Slot_Availability,
    Retrieve_User_Bookings,
    Cancel_Reservation(),
    Update_Booking_Time(),
]
