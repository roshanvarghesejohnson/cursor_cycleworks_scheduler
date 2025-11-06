from django.contrib import admin
from bookings.models import CustomerBooking, AssignmentRun, AssignmentChange


@admin.register(CustomerBooking)
class CustomerBookingAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'city', 'date', 'slot', 'status', 'assigned_technician', 'created_at')
    list_filter = ('status', 'city', 'date', 'slot')
    search_fields = ('name', 'phone', 'city', 'pincode', 'address')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'date'
    
    fieldsets = (
        ('Customer Information', {
            'fields': ('name', 'phone', 'city', 'address', 'pincode')
        }),
        ('Location', {
            'fields': ('lat', 'lng')
        }),
        ('Booking Details', {
            'fields': ('date', 'slot')
        }),
        ('Assignment', {
            'fields': ('assigned_technician', 'status')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(AssignmentRun)
class AssignmentRunAdmin(admin.ModelAdmin):
    list_display = ('city', 'date', 'run_at', 'before_total_km', 'after_total_km', 'distance_saved_km', 'groups_optimized')
    list_filter = ('city', 'date', 'run_at')
    search_fields = ('city',)
    readonly_fields = ('run_at',)
    date_hierarchy = 'run_at'
    
    fieldsets = (
        ('Run Information', {
            'fields': ('city', 'date', 'run_at')
        }),
        ('Metrics', {
            'fields': ('before_total_km', 'after_total_km', 'distance_saved_km', 'groups_optimized')
        }),
        ('Metadata', {
            'fields': ('meta',),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related('changes')


@admin.register(AssignmentChange)
class AssignmentChangeAdmin(admin.ModelAdmin):
    list_display = ('run', 'slot', 'customer_name', 'old_technician', 'new_technician', 'old_km', 'new_km', 'delta_km', 'changed')
    list_filter = ('run', 'slot', 'changed', 'run__city', 'run__date')
    search_fields = ('customer_name', 'customer_pincode', 'old_technician', 'new_technician')
    readonly_fields = ('run', 'booking', 'slot', 'customer_name', 'customer_pincode', 
                      'old_technician', 'new_technician', 'old_km', 'new_km', 'delta_km', 'changed')
    
    def has_add_permission(self, request):
        return False  # Changes are created automatically by optimization runs
