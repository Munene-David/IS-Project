from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ('STUDENT', 'University Student'),
        ('HOUSEHOLD', 'Household Owner'),
        ('ADMIN', 'Administrator'),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='STUDENT')
    phone_number = models.CharField(max_length=20, unique=False, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    def is_student(self):
        return self.role == 'STUDENT'

    def is_household(self):
        return self.role == 'HOUSEHOLD'

    def is_system_admin(self):
        return self.role == 'ADMIN' or self.is_superuser

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class StudentProfile(models.Model):
    VERIFICATION_CHOICES = (
        ('Pending', 'Pending'),
        ('Verified', 'Verified'),
        ('Rejected', 'Rejected'),
    )

    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='student_profile')
    university_id = models.CharField(max_length=50, blank=True)
    university_name = models.CharField(max_length=150, blank=True)
    verification_status = models.CharField(max_length=20, choices=VERIFICATION_CHOICES, default='Pending')
    availability_status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Broadcast-matching fields
    categories_offered = models.JSONField(default=list, blank=True)  # e.g. ["Cleaning", "Laundry"]
    location_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    location_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    cancellation_count = models.IntegerField(default=0)
    reliability_score = models.FloatField(default=1.0)  # ranking multiplier, lowered on cancellations
    is_flagged = models.BooleanField(default=False)  # flagged to admin for repeated cancellations

    def __str__(self):
        return f"Student: {self.user.username} ({self.university_name})"

    def record_cancellation(self):
        """Lower reliability after a post-acceptance cancellation.
        Three or more cancellations flags the account to the admin."""
        self.cancellation_count += 1
        self.reliability_score = max(0.3, self.reliability_score * 0.85)
        if self.cancellation_count >= 3:
            self.is_flagged = True
        self.save(update_fields=['cancellation_count', 'reliability_score', 'is_flagged'])


class HouseholdProfile(models.Model):
    VERIFICATION_CHOICES = (
        ('Pending', 'Pending'),
        ('Verified', 'Verified'),
        ('Rejected', 'Rejected'),
    )

    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='household_profile')
    address = models.TextField(blank=True)
    location_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    location_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    verification_status = models.CharField(max_length=20, choices=VERIFICATION_CHOICES, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)

    # Broadcast-matching settings
    min_rating = models.DecimalField(max_digits=3, decimal_places=1, default=0)  # minimum student rating
    search_radius_km = models.DecimalField(max_digits=5, decimal_places=1, default=5)  # default broadcast radius

    def __str__(self):
        return f"Household: {self.user.username} - {self.address[:30] if self.address else 'No address'}"


class BlockedStudent(models.Model):
    """A household's block list — blocked students are excluded from matching."""
    household = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='blocked_students')
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='blocked_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('household', 'student')

    def __str__(self):
        return f"{self.household.username} blocked {self.student.username}"


class AdminProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='admin_profile')
    admin_level = models.IntegerField(default=1)
    department = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Admin: {self.user.username} (Lvl {self.admin_level})"


@receiver(post_save, sender=CustomUser)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        if instance.role == 'STUDENT' and not hasattr(instance, 'student_profile'):
            StudentProfile.objects.create(user=instance)
        elif instance.role == 'HOUSEHOLD' and not hasattr(instance, 'household_profile'):
            HouseholdProfile.objects.create(user=instance)
        elif instance.role == 'ADMIN' and not hasattr(instance, 'admin_profile'):
            AdminProfile.objects.create(user=instance)


# Import Notification so it's part of this app's models
from .notifications import Notification  # noqa: F401, E402


__all__ = [
    'CustomUser', 'StudentProfile', 'HouseholdProfile', 'AdminProfile',
    'BlockedStudent', 'Notification',
]
