"""
Slot generation utility for creating availability slots for technicians.
"""
from datetime import date
from typing import Tuple

from django.db import transaction

from technicians.models import Technician, AvailabilitySlot


# Standard slot windows: 2-hour slots
STANDARD_SLOTS = ['09_11', '11_13', '13_15', '15_17', '17_19']


def generate_slots_for_date(target_date: date) -> Tuple[int, int]:
    """
    Generate standard 2-hour availability slots for all active technicians on a given date.
    
    This function creates slots for each active technician for the specified date.
    It will not create duplicate slots if they already exist (enforced by unique_together
    constraint in the AvailabilitySlot model).
    
    Args:
        target_date: The date for which to generate slots (date object)
        
    Returns:
        A tuple of (created_count, skipped_count) where:
        - created_count: Number of slots successfully created
        - skipped_count: Number of slots that already existed (duplicates)
        
    Example:
        >>> from datetime import date
        >>> created, skipped = generate_slots_for_date(date(2025, 1, 15))
        >>> print(f"Created {created} slots, skipped {skipped} duplicates")
    """
    # Get all active technicians
    active_technicians = Technician.objects.filter(is_active=True)
    
    created_count = 0
    skipped_count = 0
    
    # Use transaction to ensure atomicity
    with transaction.atomic():
        for technician in active_technicians:
            for slot_code in STANDARD_SLOTS:
                # Use get_or_create to avoid duplicates
                # This will create the slot if it doesn't exist, or return existing one
                slot, created = AvailabilitySlot.objects.get_or_create(
                    technician=technician,
                    date=target_date,
                    slot=slot_code,
                    defaults={'is_booked': False}
                )
                
                if created:
                    created_count += 1
                else:
                    skipped_count += 1
    
    return created_count, skipped_count

