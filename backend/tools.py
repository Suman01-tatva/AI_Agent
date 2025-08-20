from typing import Optional
from langchain_core.tools import tool, BaseTool
from pydantic import BaseModel, Field
from datetime import date
from dotenv import load_dotenv

from tools_utils import (
    check_and_save_slot,
    get_user_slot,
    cancel_slot,
    update_slot,
)

load_dotenv()
today_str = date.today().isoformat()

# --- Input Schemas ---
class ReservationInput(BaseModel):
    name: str = Field(..., description="Name of the user, e.g., John, Suman")
    contact: str = Field(..., min_length=10, max_length=10, description="10-digit contact number, digits only (e.g., 9876543210)")
    time: str = Field(..., description="Convert time in HH:MM:SS format, must be between restaurant opening hours")
    guests: int = Field(..., gt=0, description="Number of people, > 0")
    date: str = Field(..., description=f"Date in YYYY-MM-DD format, > {today_str}")

class CancelInput(BaseModel):
    slot_id: int = Field(...,gt=0, description="ID of the booking to cancel, must be greater than 0")

class UpdateBookingInput(BaseModel):
    id: int
    bookingName: str = Field(..., description="Name of the user, e.g., John, Suman")
    contactNumber: str = Field(..., min_length=10, max_length=10,description="10-digit contact number, digits only (e.g., 9876543210)")
    bookingDate: str = Field(..., description=f"Date in YYYY-MM-DD format, > {today_str}")
    bookingTime: str = Field(..., description="Convert time in HH:MM:SS format, must be between restaurant opening hours")
    noOfPeople: int = Field(..., gt=0, description="Number of people, > 0")

class RetrieveInput(BaseModel):
    name: Optional[str] = Field(..., description="Name of the user, e.g., John, Suman")
    contact: Optional[str] = Field(..., min_length=10, max_length=10,description="10-digit contact number, digits only (e.g., 9876543210)")

# --- Tools ---  

@tool(args_schema=ReservationInput)
def Save_Reservation(name: str, contact: str, time: str, guests: int, date: str) -> str:
    """
    Save a reservation if the selected slot is available, and take time slot of one hour.
    Validates input before making the booking.
    """
    return check_and_save_slot(name, contact, time, guests, date)

@tool(args_schema=RetrieveInput)
def Retrieve_User_Bookings(name: Optional[str] = None, contact: Optional[str] = None):
    """Retrieve all bookings for a user using name or contact."""
    return get_user_slot(name=name, contact=contact)

@tool(args_schema=CancelInput)
def Cancel_Reservation(slot_id: int) -> str:
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
 