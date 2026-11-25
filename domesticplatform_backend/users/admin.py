from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, StudentProfile, HouseholdProfile, AdminProfile


class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Platform Details', {'fields': ('role', 'phone_number')}),
    )
    list_display = ['username', 'email', 'role', 'phone_number', 'is_staff']
    list_filter = ['role', 'is_staff', 'is_active']


admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(StudentProfile)
admin.site.register(HouseholdProfile)
admin.site.register(AdminProfile)
