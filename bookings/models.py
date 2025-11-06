from django.db import models
from technicians.models import Technician, AvailabilitySlot


class CustomerBooking(models.Model):
    """Model for customer booking requests."""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('assigned', 'Assigned'),
        ('completed', 'Completed'),
    ]
    
    # Customer information
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    city = models.CharField(max_length=100)
    address = models.TextField()
    pincode = models.CharField(max_length=10)
    
    # Location coordinates (populated from pincode lookup)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    
    # Booking details
    date = models.DateField()
    slot = models.CharField(max_length=10, choices=AvailabilitySlot.SLOT_CHOICES)
    
    # Assignment
    assigned_technician = models.ForeignKey(
        Technician,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bookings'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Customer Booking'
        verbose_name_plural = 'Customer Bookings'
    
    def __str__(self):
        technician_info = f" → {self.assigned_technician.name}" if self.assigned_technician else ""
        return f"{self.name} - {self.date} [{self.get_slot_display()}] ({self.status}){technician_info}"


class AssignmentRun(models.Model):
    """Tracks optimization runs for a city/date combination."""
    
    city = models.CharField(max_length=100)
    date = models.DateField()
    run_at = models.DateTimeField(auto_now_add=True)
    
    # Metrics
    before_total_km = models.FloatField()
    after_total_km = models.FloatField()
    distance_saved_km = models.FloatField()
    groups_optimized = models.IntegerField(default=0)
    
    # Additional metadata (per-slot, per-tech breakdowns)
    meta = models.JSONField(default=dict, blank=True)
    
    class Meta:
        ordering = ['-run_at']
        verbose_name = 'Assignment Run'
        verbose_name_plural = 'Assignment Runs'
        indexes = [
            models.Index(fields=['city', 'date']),
            models.Index(fields=['-run_at']),
        ]
    
    def __str__(self):
        return f"{self.city} - {self.date} ({self.run_at.strftime('%Y-%m-%d %H:%M')}) - Saved {self.distance_saved_km:.2f} km"


class AssignmentChange(models.Model):
    """Tracks individual booking assignment changes in an optimization run."""
    
    run = models.ForeignKey(AssignmentRun, on_delete=models.CASCADE, related_name='changes')
    booking = models.ForeignKey(CustomerBooking, on_delete=models.CASCADE, related_name='assignment_changes')
    
    slot = models.CharField(max_length=10)
    customer_name = models.CharField(max_length=100)
    customer_pincode = models.CharField(max_length=10)
    
    old_technician = models.CharField(max_length=100, null=True, blank=True)
    new_technician = models.CharField(max_length=100, null=True, blank=True)
    
    old_km = models.FloatField()
    new_km = models.FloatField()
    delta_km = models.FloatField()
    changed = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['run', 'slot', 'customer_name']
        verbose_name = 'Assignment Change'
        verbose_name_plural = 'Assignment Changes'
        indexes = [
            models.Index(fields=['run', 'changed']),
        ]
    
    def __str__(self):
        change_indicator = "✓" if self.changed else "—"
        return f"{change_indicator} {self.customer_name} ({self.slot}): {self.old_technician} → {self.new_technician}"
