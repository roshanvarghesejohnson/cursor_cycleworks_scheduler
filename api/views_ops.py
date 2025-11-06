"""
Operations views for staff-only optimization dashboard.
"""
import json
import logging
from datetime import date
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from bookings.models import CustomerBooking
from bookings.services.optimizer import preview_optimization, apply_optimization

logger = logging.getLogger(__name__)


@staff_member_required
def schedule_view(request):
    """Main schedule optimization dashboard."""
    # Get city and date from query params
    city = request.GET.get('city', '')
    date_str = request.GET.get('date', '')
    
    # Default to first city found and today
    if not city:
        first_booking = CustomerBooking.objects.filter(
            status='assigned'
        ).values_list('city', flat=True).distinct().first()
        city = first_booking or 'Mumbai'
    
    if not date_str:
        target_date = date.today()
    else:
        try:
            target_date = parse_date(date_str)
            if target_date is None:
                target_date = date.today()
        except (ValueError, TypeError):
            target_date = date.today()
    
    # Get available cities
    cities = CustomerBooking.objects.filter(
        status='assigned'
    ).values_list('city', flat=True).distinct().order_by('city')
    
    # Get preview data
    preview_data = None
    try:
        preview_data = preview_optimization(city, target_date)
    except Exception as e:
        logger.error(f"Error generating preview: {e}", exc_info=True)
    
    # Build technician assignments data
    technician_assignments = {}
    if preview_data:
        # Group assignments by technician
        for assignment in preview_data['before']['assignments']:
            tech_name = assignment['tech_name']
            if tech_name not in technician_assignments:
                technician_assignments[tech_name] = {
                    'before': [],
                    'after': []
                }
            technician_assignments[tech_name]['before'].append(assignment)
        
        # Add after assignments
        for assignment in preview_data['after']['assignments']:
            tech_name = assignment['tech_name']
            if tech_name not in technician_assignments:
                technician_assignments[tech_name] = {
                    'before': [],
                    'after': []
                }
            technician_assignments[tech_name]['after'].append(assignment)
    
    context = {
        'city': city,
        'date': target_date.isoformat(),
        'cities': cities,
        'preview_data': preview_data,
        'technician_assignments': technician_assignments
    }
    
    return render(request, 'ops/schedule.html', context)


@staff_member_required
@csrf_protect
@require_http_methods(["POST"])
def preview_api(request):
    """API endpoint for preview optimization."""
    try:
        data = json.loads(request.body)
        city = data.get('city')
        date_str = data.get('date')
        
        if not city or not date_str:
            return JsonResponse({'error': 'city and date are required'}, status=400)
        
        target_date = parse_date(date_str)
        if target_date is None:
            return JsonResponse({'error': 'Invalid date format'}, status=400)
        
        preview = preview_optimization(city, target_date)
        return JsonResponse(preview)
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error in preview_api: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@staff_member_required
@csrf_protect
@require_http_methods(["POST"])
def apply_api(request):
    """API endpoint for applying optimization."""
    try:
        data = json.loads(request.body)
        city = data.get('city')
        date_str = data.get('date')
        
        if not city or not date_str:
            return JsonResponse({'error': 'city and date are required'}, status=400)
        
        target_date = parse_date(date_str)
        if target_date is None:
            return JsonResponse({'error': 'Invalid date format'}, status=400)
        
        run = apply_optimization(city, target_date)
        
        return JsonResponse({
            'run_id': run.id,
            'before_total_km': run.before_total_km,
            'after_total_km': run.after_total_km,
            'saved_km': run.distance_saved_km,
            'groups_optimized': run.groups_optimized
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error in apply_api: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

