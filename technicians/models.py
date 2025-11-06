from django.db import models
from django.utils import timezone

class Technician(models.Model):
    name = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    current_lat = models.FloatField(null=True, blank=True)
    current_lng = models.FloatField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.city})"


class AvailabilitySlot(models.Model):
    SLOT_CHOICES = [
        ('09_11', '09:00–11:00'),
        ('11_13', '11:00–13:00'),
        ('13_15', '13:00–15:00'),
        ('15_17', '15:00–17:00'),
        ('17_19', '17:00–19:00'),
    ]

    technician = models.ForeignKey(Technician, on_delete=models.CASCADE, related_name='slots')
    date = models.DateField(default=timezone.now)
    slot = models.CharField(max_length=10, choices=SLOT_CHOICES)
    is_booked = models.BooleanField(default=False)

    class Meta:
        unique_together = ('technician', 'date', 'slot')

    def __str__(self):
        return f"{self.technician.name} – {self.date} [{self.get_slot_display()}]"
