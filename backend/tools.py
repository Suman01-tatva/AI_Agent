from typing import Optional
from langchain_core.tools import tool, BaseTool
from pydantic import BaseModel, Field
from typing import ClassVar
from langchain_community.tools.tavily_search import TavilySearchResults
from datetime import date

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

today = date.today().isoformat()
# --- Input Schemas ---
class ReservationInput(BaseModel):
    """Input schema for creating or saving a reservation."""

    name: str = Field(
        description="Name of the person making the reservation.",
    )
    contact: str = Field(
        description="Contact number, must be a valid phone number.",
    )
    time: str = Field(
        description="Preferred time in HH:mm:ss format, must be within operating hours.",
    )
    guests: int = Field(
        ge=1,
        description="Number of guests, must be at least 1.",
    )
    date: str = Field(
        description=f"Date in YYYY-MM-DD format and must be > {today}.",
    )


class DateInput(BaseModel):
    """Input schema for checking availability on a specific date and time."""
    date: str = Field(
        default_factory=lambda: date.today().isoformat(),
        description=f"Date in YYYY-MM-DD format and must be > {today}.",
    )
    time: Optional[str] = Field(
        default=None,
        description="Optional time in HH:mm:ss format. If not provided, checks availability for the entire day.",
    )


class CancelInput(BaseModel):
    """Input schema for cancelling a reservation by ID."""
    slot_id: int = Field(
        description="ID of the reservation to cancel.",
        ge=1,
    )


class UpdateBookingInput(BaseModel):
    """Input schema for updating a booking."""
    id: int = Field(
        description="ID of the booking to update.",
        ge=1,
    )
    bookingName: str = Field(
        description="Updated name for the booking.",
    )
    contactNumber: str = Field(...,min_length=10, max_length=13,
        description="Updated contact number for the booking. Must be a valid phone number. Takes 10-13 digits.",
    )
    bookingDate: str = Field(
        description="Updated date for the booking in YYYY-MM-DD format. Must be greater than today.",
    )
    bookingTime: str = Field(
        description="Updated time for the booking in HH:mm:ss format. Must be within operating hours.",
    )
    noOfPeople: int = Field(
        ge=1,
        description="Updated number of guests for the booking, must be at least 1.",
    )


class RetrieveInput(BaseModel):
    """Input schema for retrieving bookings using optional name or contact."""
    name: str = Field(
        description="Name of the person to retrieve bookings.",
    )
    contact: str = Field(
        description="Contact number of the person to retrieve bookings.",
    )


# --- Tools ---
@tool(args_schema=ReservationInput)
def Create_User_Details(
    name: str, contact: str, time: str, guests: int, date: str
) -> str:
    """Collect booking details before confirmation."""
    return (
        f"Booking details:\n"
        f"Name: {name}\n"
        f"Contact: {contact}\n"
        f"Date: {date}\n"
        f"Time: {time}\n"
        f"Guests: {guests}\n"
        f"Reply with 'Yes' to confirm or update the details."
    )


@tool(args_schema=ReservationInput)
def Save_Reservation(name: str, contact: str, time: str, guests: int, date: str) -> str:
    """Save a reservation if the selected slot is available, and take time slot of one hour."""
    slot_status = is_slot_available(date, time, guests)
    if slot_status is None:
        return "Unable to check availability at the moment. Please try again later."
    elif slot_status:
        return insert_booking(name, contact, time, guests, date)
    return f"Sorry, booking is full or the slot at {time} on {date} is already booked. Try another time."

@tool(args_schema=DateInput)
def Check_Slot_Availability(date: str, time: Optional[str] = None) -> str:
    """Check whether a time slot is available on a specific date."""
    slot_status = is_slot_available(date, time,guests=1)
    if slot_status is None:
        return "Unable to check availability at the moment. Please try again later."
    elif slot_status:
        return f"Slot available at {time} on {date}."
    elif slot_status is False:
        return f"Booking full or slot not available on {date, time}."


@tool(args_schema=RetrieveInput)
def Retrieve_User_Bookings(name: str, contact: str) -> str:
    """Retrieve all active or cancelled bookings for a user using name and contact."""
    result = get_user_slot(name=name, contact=contact)
    if isinstance(result, dict) and "Error" in str(result):
        return f"Error retrieving bookings: {result}"
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