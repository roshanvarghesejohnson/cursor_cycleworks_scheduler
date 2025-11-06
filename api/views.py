import math
from datetime import date
from django.utils.dateparse import parse_date
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from technicians.models import AvailabilitySlot, Technician
from bookings.models import CustomerBooking
from bookings.utils.coords import get_coords_from_pincode


class AvailableSlotsView(APIView):
    """
    API endpoint to get available slots for a given city and date.
    
    Query parameters:
        - city (required): City name to filter technicians
        - date (required): Date in YYYY-MM-DD format
    
    Returns:
        JSON with date, city, and list of available slots with codes and labels
    """
    
    def get(self, request):
        # Get query parameters
        city = request.query_params.get('city')
        date_str = request.query_params.get('date')
        
        # Validate required parameters
        if not city:
            return Response(
                {'error': 'city parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not date_str:
            return Response(
                {'error': 'date parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Parse date
        try:
            target_date = parse_date(date_str)
            if target_date is None:
                raise ValueError("Invalid date format")
        except (ValueError, TypeError):
            return Response(
                {'error': f'Invalid date format: "{date_str}". Please use YYYY-MM-DD format.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Query available slots
        # Filter by: technician.city, date, and is_booked=False
        available_slots = AvailabilitySlot.objects.filter(
            technician__city=city,
            date=target_date,
            is_booked=False
        ).select_related('technician')
        
        # Get unique slot codes and their labels
        slot_dict = {}
        for slot in available_slots:
            slot_code = slot.slot
            if slot_code not in slot_dict:
                slot_dict[slot_code] = slot.get_slot_display()
        
        # Build response
        available_slots_list = [
            {'slot': slot_code, 'label': label}
            for slot_code, label in sorted(slot_dict.items())
        ]
        
        return Response({
            'date': date_str,
            'city': city,
            'available_slots': available_slots_list
        })


def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points on Earth using the Haversine formula.
    
    Args:
        lat1, lon1: Latitude and longitude of first point in decimal degrees
        lat2, lon2: Latitude and longitude of second point in decimal degrees
    
    Returns:
        Distance in kilometers
    """
    # Earth radius in kilometers
    R = 6371.0
    
    # Convert degrees to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    # Haversine formula
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    distance = R * c
    return distance


class BookView(APIView):
    """
    API endpoint to create a booking with automatic technician assignment.
    
    Request body (JSON):
        - name (required): Customer name
        - phone (required): Customer phone number
        - city (required): City name
        - address (required): Customer address
        - pincode (required): Pincode
        - date (required): Date in YYYY-MM-DD format
        - slot (required): Slot code (e.g., "09_11")
    
    Returns:
        JSON with status and assigned technician name
    """
    
    def post(self, request):
        # Get request data
        name = request.data.get('name')
        phone = request.data.get('phone')
        city = request.data.get('city')
        address = request.data.get('address')
        pincode = request.data.get('pincode')
        date_str = request.data.get('date')
        slot = request.data.get('slot')
        
        # Validate required fields
        required_fields = ['name', 'phone', 'city', 'address', 'pincode', 'date', 'slot']
        missing_fields = [field for field in required_fields if not request.data.get(field)]
        
        if missing_fields:
            return Response(
                {'error': f'Missing required fields: {", ".join(missing_fields)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Parse date
        try:
            target_date = parse_date(date_str)
            if target_date is None:
                raise ValueError("Invalid date format")
        except (ValueError, TypeError):
            return Response(
                {'error': f'Invalid date format: "{date_str}". Please use YYYY-MM-DD format.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate slot
        valid_slots = [choice[0] for choice in AvailabilitySlot.SLOT_CHOICES]
        if slot not in valid_slots:
            return Response(
                {'error': f'Invalid slot: "{slot}". Valid slots are: {", ".join(valid_slots)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get coordinates from pincode
        coords = get_coords_from_pincode(pincode)
        if coords is None:
            return Response(
                {'error': f'Pincode "{pincode}" not found in lookup table'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        customer_lat, customer_lng = coords
        
        # Query available slots for the given city, date, and slot
        available_slots = AvailabilitySlot.objects.filter(
            technician__city=city,
            date=target_date,
            slot=slot,
            is_booked=False
        ).select_related('technician')
        
        if not available_slots.exists():
            return Response(
                {'error': 'No technicians available'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Calculate distance for each available technician
        technician_distances = []
        for slot_obj in available_slots:
            technician = slot_obj.technician
            
            # Use technician's current location if available
            if technician.current_lat is not None and technician.current_lng is not None:
                distance = haversine_distance(
                    customer_lat, customer_lng,
                    technician.current_lat, technician.current_lng
                )
            else:
                # If technician has no current location, assign a very large distance
                # so they are selected last (only if all technicians have no location)
                distance = float('inf')
            
            technician_distances.append((slot_obj, technician, distance))
        
        # Sort by distance (nearest first)
        technician_distances.sort(key=lambda x: x[2])
        
        # Select the nearest technician's slot
        selected_slot, selected_technician, _ = technician_distances[0]
        
        # Create booking and update slot in a transaction
        try:
            with transaction.atomic():
                # Mark the slot as booked
                selected_slot.is_booked = True
                selected_slot.save()
                
                # Create customer booking
                booking = CustomerBooking.objects.create(
                    name=name,
                    phone=phone,
                    city=city,
                    address=address,
                    pincode=pincode,
                    lat=customer_lat,
                    lng=customer_lng,
                    date=target_date,
                    slot=slot,
                    assigned_technician=selected_technician,
                    status='assigned'
                )
                
                # Update technician's current location to customer location
                selected_technician.current_lat = customer_lat
                selected_technician.current_lng = customer_lng
                selected_technician.save()
            
            return Response({
                'status': 'success',
                'assigned_technician': selected_technician.name
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response(
                {'error': f'Error creating booking: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
