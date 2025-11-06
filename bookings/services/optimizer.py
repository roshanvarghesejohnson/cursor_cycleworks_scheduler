"""
Optimization service for technician assignments.

Provides preview and apply functions for optimizing technician assignments
using the Hungarian algorithm to minimize total travel distance.
"""
import logging
import numpy as np
from collections import defaultdict
from datetime import date
from typing import Dict, List, Tuple, Optional

from django.db import transaction
from scipy.optimize import linear_sum_assignment

from bookings.models import CustomerBooking, AssignmentRun, AssignmentChange
from technicians.models import AvailabilitySlot, Technician
from bookings.utils.coords import haversine_distance

logger = logging.getLogger(__name__)

# Slot order for route calculation
SLOT_ORDER = ['09_11', '11_13', '13_15', '15_17', '17_19']


def _build_current_state(city: str, target_date: date) -> Dict:
    """
    Build current state metrics for a city/date.
    
    Returns:
        Dict with total_km, per_slot, per_tech, assignments
    """
    bookings = CustomerBooking.objects.filter(
        date=target_date,
        city=city,
        status='assigned',
        assigned_technician__isnull=False,
        lat__isnull=False,
        lng__isnull=False
    ).select_related('assigned_technician')
    
    total_km = 0.0
    per_slot = defaultdict(float)
    per_tech = defaultdict(float)
    assignments = []
    
    for booking in bookings:
        tech = booking.assigned_technician
        if tech and tech.current_lat and booking.lat:
            dist = haversine_distance(
                booking.lat, booking.lng,
                tech.current_lat, tech.current_lng
            )
            total_km += dist
            per_slot[booking.slot] += dist
            per_tech[tech.name] += dist
            
            assignments.append({
                'booking_id': booking.id,
                'customer_name': booking.name,
                'slot': booking.slot,
                'tech_name': tech.name,
                'distance_km': dist
            })
    
    return {
        'total_km': total_km,
        'per_slot': dict(per_slot),
        'per_tech': dict(per_tech),
        'assignments': assignments
    }


def _calculate_route_distance(tech_name: str, assignments_by_slot: Dict[str, List]) -> float:
    """
    Calculate total route distance for a technician by chaining slots in time order.
    
    Args:
        tech_name: Technician name
        assignments_by_slot: Dict mapping slot -> list of (booking, tech, distance) tuples
    
    Returns:
        Total route distance in km
    """
    # Get technician's starting location
    tech = Technician.objects.filter(name=tech_name).first()
    if not tech or not tech.current_lat:
        return 0.0
    
    current_lat, current_lng = tech.current_lat, tech.current_lng
    total_route = 0.0
    
    # Collect all bookings for this technician, sorted by slot order
    tech_bookings = []
    for slot in SLOT_ORDER:
        if slot not in assignments_by_slot:
            continue
        for booking, assigned_tech, _ in assignments_by_slot[slot]:
            if assigned_tech.name == tech_name and booking.lat:
                tech_bookings.append((slot, booking))
    
    # Calculate route by visiting each booking in slot order
    for slot, booking in tech_bookings:
        if booking.lat:
            # Distance from current position to customer
            dist = haversine_distance(
                current_lat, current_lng,
                booking.lat, booking.lng
            )
            total_route += dist
            # Update current position to customer location
            current_lat, current_lng = booking.lat, booking.lng
    
    return total_route


def _optimize_slot_group(
    city: str, 
    slot: str, 
    bookings: List[CustomerBooking], 
    target_date: date
) -> Tuple[Dict, List[Tuple]]:
    """
    Optimize assignments for a single slot group using Hungarian algorithm.
    
    Returns:
        Tuple of (optimization_result_dict, optimized_assignments_list)
        optimized_assignments_list contains (booking, technician, distance) tuples
    """
    # Get technicians with booked slots for this group
    booked_slots = AvailabilitySlot.objects.filter(
        technician__city=city,
        date=target_date,
        slot=slot,
        is_booked=True
    ).select_related('technician')
    
    technicians = []
    technician_dict = {}
    for slot_obj in booked_slots:
        tech = slot_obj.technician
        if tech.id not in technician_dict:
            technicians.append(tech)
            technician_dict[tech.id] = tech
    
    # Get customer coordinates
    customer_coords = []
    for booking in bookings:
        if booking.lat is not None and booking.lng is not None:
            customer_coords.append((booking.lat, booking.lng, booking))
    
    if not customer_coords or not technicians:
        return None, []
    
    # Calculate current total distance
    old_total_distance = 0.0
    for booking in bookings:
        tech = booking.assigned_technician
        if tech and tech.current_lat and booking.lat:
            old_total_distance += haversine_distance(
                booking.lat, booking.lng,
                tech.current_lat, tech.current_lng
            )
    
    # Build distance matrix
    num_techs = len(technicians)
    num_bookings = len(customer_coords)
    max_size = max(num_techs, num_bookings)
    distance_matrix = np.full((max_size, max_size), 1e6)
    
    for i, tech in enumerate(technicians):
        tech_lat = tech.current_lat if tech.current_lat is not None else None
        tech_lng = tech.current_lng if tech.current_lng is not None else None
        
        for j, (cust_lat, cust_lng, booking) in enumerate(customer_coords):
            if tech_lat is not None and tech_lng is not None:
                distance_matrix[i, j] = haversine_distance(
                    tech_lat, tech_lng,
                    cust_lat, cust_lng
                )
    
    # Run Hungarian algorithm
    row_indices, col_indices = linear_sum_assignment(distance_matrix)
    
    # Build optimized assignments
    new_total_distance = 0.0
    optimized_assignments = []
    
    for i, j in zip(row_indices, col_indices):
        if i < num_techs and j < num_bookings:
            tech = technicians[i]
            cust_lat, cust_lng, booking = customer_coords[j]
            
            if tech.current_lat is not None and tech.current_lng is not None:
                dist = haversine_distance(
                    tech.current_lat, tech.current_lng,
                    cust_lat, cust_lng
                )
                new_total_distance += dist
                optimized_assignments.append((booking, tech, dist))
    
    improvement = old_total_distance - new_total_distance
    
    return {
        'slot': slot,
        'old_distance': old_total_distance,
        'new_distance': new_total_distance,
        'improvement_km': improvement,
        'improved': improvement >= 0.01
    }, optimized_assignments


def preview_optimization(city: str, target_date: date) -> Dict:
    """
    Preview optimization without applying changes.
    
    Returns:
        Dict with before, after, changes, groups_optimized, distance_saved_km
    """
    logger.debug(f"Previewing optimization for {city} on {target_date}")
    
    # Build current state
    before = _build_current_state(city, target_date)
    
    # Get all bookings grouped by slot
    bookings = CustomerBooking.objects.filter(
        date=target_date,
        city=city,
        status='assigned',
        assigned_technician__isnull=False,
        lat__isnull=False,
        lng__isnull=False
    ).select_related('assigned_technician')
    
    grouped_bookings = defaultdict(list)
    for booking in bookings:
        grouped_bookings[booking.slot].append(booking)
    
    # Optimize each slot group
    after_total_km = 0.0
    after_per_slot = defaultdict(float)
    after_per_tech = defaultdict(float)
    after_assignments = []
    changes = []
    groups_optimized = 0
    optimized_assignments_by_slot = defaultdict(list)
    
    for slot, slot_bookings in sorted(grouped_bookings.items()):
        opt_result, optimized = _optimize_slot_group(city, slot, slot_bookings, target_date)
        
        if opt_result and opt_result['improved']:
            groups_optimized += 1
        
        # Build after state from optimized assignments
        for booking, tech, dist in optimized:
            after_total_km += dist
            after_per_slot[slot] += dist
            after_per_tech[tech.name] += dist
            
            after_assignments.append({
                'booking_id': booking.id,
                'customer_name': booking.name,
                'slot': slot,
                'tech_name': tech.name,
                'distance_km': dist
            })
            
            optimized_assignments_by_slot[slot].append((booking, tech, dist))
            
            # Build change record
            old_tech = booking.assigned_technician
            old_tech_name = old_tech.name if old_tech else None
            old_km = 0.0
            if old_tech and old_tech.current_lat and booking.lat:
                old_km = haversine_distance(
                    booking.lat, booking.lng,
                    old_tech.current_lat, old_tech.current_lng
                )
            
            changed = (old_tech != tech)
            delta_km = old_km - dist
            abs_delta_km = abs(delta_km) if delta_km < 0 else delta_km
            
            changes.append({
                'booking_id': booking.id,
                'slot': slot,
                'customer_name': booking.name,
                'old_technician': old_tech_name,
                'new_technician': tech.name,
                'old_km': old_km,
                'new_km': dist,
                'delta_km': delta_km,
                'abs_delta_km': abs_delta_km,
                'changed': changed
            })
    
    # Calculate route distances per technician for after state
    after_per_tech_routes = {}
    for tech_name in after_per_tech.keys():
        route_dist = _calculate_route_distance(tech_name, optimized_assignments_by_slot)
        after_per_tech_routes[tech_name] = route_dist
    
    # Calculate route distances for before state
    before_assignments_by_slot = defaultdict(list)
    for booking in bookings:
        tech = booking.assigned_technician
        if tech and booking.lat:
            before_assignments_by_slot[booking.slot].append((booking, tech, 0.0))
    
    before_per_tech_routes = {}
    for tech_name in before['per_tech'].keys():
        route_dist = _calculate_route_distance(tech_name, before_assignments_by_slot)
        before_per_tech_routes[tech_name] = route_dist
    
    distance_saved_km = before['total_km'] - after_total_km
    
    return {
        'before': {
            'total_km': before['total_km'],
            'per_slot': before['per_slot'],
            'per_tech': before['per_tech'],
            'per_tech_routes': before_per_tech_routes,
            'assignments': before['assignments']
        },
        'after': {
            'total_km': after_total_km,
            'per_slot': dict(after_per_slot),
            'per_tech': dict(after_per_tech),
            'per_tech_routes': after_per_tech_routes,
            'assignments': after_assignments
        },
        'changes': changes,
        'groups_optimized': groups_optimized,
        'distance_saved_km': distance_saved_km
    }


def apply_optimization(city: str, target_date: date) -> AssignmentRun:
    """
    Apply optimization and create AssignmentRun/AssignmentChange records.
    
    Returns:
        AssignmentRun instance
    """
    logger.debug(f"Applying optimization for {city} on {target_date}")
    
    # Get preview first
    preview = preview_optimization(city, target_date)
    
    with transaction.atomic():
        # Apply changes to bookings
        bookings_dict = {b.id: b for b in CustomerBooking.objects.filter(
            date=target_date,
            city=city,
            status='assigned'
        ).select_related('assigned_technician')}
        
        for change in preview['changes']:
            booking = bookings_dict.get(change['booking_id'])
            if not booking:
                continue
            
            new_tech = Technician.objects.filter(name=change['new_technician']).first()
            old_tech = booking.assigned_technician
            
            if new_tech and old_tech != new_tech:
                # Update booking assignment
                booking.assigned_technician = new_tech
                booking.save()
                
                # Update AvailabilitySlot: unbook old tech's slot, book new tech's slot
                # Find and unbook old tech's slot
                if old_tech:
                    old_slot = AvailabilitySlot.objects.filter(
                        technician=old_tech,
                        date=target_date,
                        slot=booking.slot,
                        is_booked=True
                    ).first()
                    if old_slot:
                        old_slot.is_booked = False
                        old_slot.save()
                
                # Find and book new tech's slot
                new_slot = AvailabilitySlot.objects.filter(
                    technician=new_tech,
                    date=target_date,
                    slot=booking.slot,
                    is_booked=False
                ).first()
                if new_slot:
                    new_slot.is_booked = True
                    new_slot.save()
        
        # Create AssignmentRun
        run = AssignmentRun.objects.create(
            city=city,
            date=target_date,
            before_total_km=preview['before']['total_km'],
            after_total_km=preview['after']['total_km'],
            distance_saved_km=preview['distance_saved_km'],
            groups_optimized=preview['groups_optimized'],
            meta={
                'before_per_slot': preview['before']['per_slot'],
                'after_per_slot': preview['after']['per_slot'],
                'before_per_tech': preview['before']['per_tech'],
                'after_per_tech': preview['after']['per_tech'],
                'before_per_tech_routes': preview['before']['per_tech_routes'],
                'after_per_tech_routes': preview['after']['per_tech_routes']
            }
        )
        
        # Create AssignmentChange records
        for change in preview['changes']:
            booking = bookings_dict.get(change['booking_id'])
            if booking:
                AssignmentChange.objects.create(
                    run=run,
                    booking=booking,
                    slot=change['slot'],
                    customer_name=change['customer_name'],
                    customer_pincode=booking.pincode,
                    old_technician=change['old_technician'],
                    new_technician=change['new_technician'],
                    old_km=change['old_km'],
                    new_km=change['new_km'],
                    delta_km=change['delta_km'],
                    changed=change['changed']
                )
        
        logger.info(f"Optimization applied: {run}")
        return run

