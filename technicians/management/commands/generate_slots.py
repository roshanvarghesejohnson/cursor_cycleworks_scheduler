"""
Django management command to generate availability slots for technicians.

Usage:
    python manage.py generate_slots YYYY-MM-DD

Example:
    python manage.py generate_slots 2025-01-15
"""
from datetime import date
from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_date

from technicians.utils.slot_generator import generate_slots_for_date


class Command(BaseCommand):
    help = 'Generate standard 2-hour availability slots for all active technicians on a given date'

    def add_arguments(self, parser):
        parser.add_argument(
            'date',
            type=str,
            help='Date in YYYY-MM-DD format (e.g., 2025-01-15)'
        )

    def handle(self, *args, **options):
        date_str = options['date']
        
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
        
        # Generate slots
        self.stdout.write(
            self.style.WARNING(
                f'Generating slots for {target_date}...'
            )
        )
        
        try:
            created_count, skipped_count = generate_slots_for_date(target_date)
            
            # Output results
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully generated slots for {target_date}'
                )
            )
            self.stdout.write(
                f'  - Created: {created_count} new slots'
            )
            self.stdout.write(
                f'  - Skipped: {skipped_count} existing slots (duplicates)'
            )
            self.stdout.write(
                f'  - Total: {created_count + skipped_count} slots processed'
            )
            
        except Exception as e:
            raise CommandError(
                f'Error generating slots: {str(e)}'
            )

