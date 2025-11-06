"""
Django management command to optimize technician assignments for a given date.

Usage:
    python manage.py optimize_day YYYY-MM-DD [--city CITY]

Example:
    python manage.py optimize_day 2025-01-15
    python manage.py optimize_day 2025-01-15 --city Mumbai
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_date

from bookings.models import CustomerBooking
from bookings.services.optimizer import apply_optimization


class Command(BaseCommand):
    help = 'Optimize technician assignments for a given date using Hungarian algorithm to minimize total travel distance'

    def add_arguments(self, parser):
        parser.add_argument(
            'date',
            type=str,
            help='Date in YYYY-MM-DD format (e.g., 2025-01-15)'
        )
        parser.add_argument(
            '--city',
            type=str,
            help='Optional: Optimize only for a specific city'
        )

    def handle(self, *args, **options):
        date_str = options['date']
        city_filter = options.get('city')
        
        # Parse the date string
        try:
            target_date = parse_date(date_str)
            if target_date is None:
                raise ValueError("Invalid date format")
        except (ValueError, TypeError) as e:
            raise CommandError(
                f'Invalid date format: "{date_str}". '
                f'Please use YYYY-MM-DD format (e.g., 2025-01-15).'
            )
        
        # Get cities to optimize
        bookings_query = CustomerBooking.objects.filter(
            date=target_date,
            status='assigned',
            assigned_technician__isnull=False,
            lat__isnull=False,
            lng__isnull=False
        )
        
        if city_filter:
            bookings_query = bookings_query.filter(city=city_filter)
        
        cities = bookings_query.values_list('city', flat=True).distinct()
        
        if not cities:
            self.stdout.write(
                self.style.WARNING(f'No assigned bookings found for {target_date}' + 
                                 (f' in {city_filter}' if city_filter else ''))
            )
            return
        
        self.stdout.write(
            self.style.WARNING(
                f'Optimizing assignments for {target_date}...\n'
                f'Processing {len(cities)} city/cities\n'
            )
        )
        
        runs = []
        total_saved = 0.0
        total_groups = 0
        
        # Process each city
        for city in sorted(cities):
            try:
                self.stdout.write(f'Processing {city}...')
                run = apply_optimization(city, target_date)
                runs.append(run)
                total_saved += run.distance_saved_km
                total_groups += run.groups_optimized
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  ✓ {city}: Saved {run.distance_saved_km:.2f} km '
                        f'({run.groups_optimized} groups optimized)'
                    )
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'  ✗ Error optimizing {city}: {str(e)}')
                )
        
        # Print summary
        self.stdout.write('\n' + '='*80)
        self.stdout.write(self.style.SUCCESS('OPTIMIZATION SUMMARY'))
        self.stdout.write('='*80)
        
        if runs:
            self.stdout.write(
                f'\n{"City":<20} {"Before (km)":<15} {"After (km)":<15} {"Saved (km)":<15} {"Groups":<10}'
            )
            self.stdout.write('-'*80)
            
            for run in runs:
                self.stdout.write(
                    f'{run.city:<20} '
                    f'{run.before_total_km:>12.2f}  '
                    f'{run.after_total_km:>12.2f}  '
                    f'{run.distance_saved_km:>12.2f}  '
                    f'{run.groups_optimized:>8}'
                )
            
            self.stdout.write('-'*80)
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nTotal distance saved: {total_saved:.2f} km\n'
                    f'Total groups optimized: {total_groups}\n'
                    f'Runs created: {len(runs)}'
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING('\nNo optimizations applied.')
            )
