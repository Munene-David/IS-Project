from rest_framework import serializers
from .models import CustomUser, StudentProfile, HouseholdProfile, AdminProfile


class StudentProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentProfile
        fields = [
            'university_id', 'university_name', 'verification_status',
            'availability_status', 'categories_offered',
            'location_lat', 'location_lng',
            'cancellation_count', 'reliability_score', 'is_flagged',
        ]


class HouseholdProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = HouseholdProfile
        fields = [
            'address', 'location_lat', 'location_lng', 'verification_status',
            'min_rating', 'search_radius_km',
        ]


class AdminProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdminProfile
        fields = ['admin_level', 'department']


class UserSerializer(serializers.ModelSerializer):
    student_profile = StudentProfileSerializer(read_only=True)
    household_profile = HouseholdProfileSerializer(read_only=True)
    admin_profile = AdminProfileSerializer(read_only=True)

    class Meta:
        model = CustomUser
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'phone_number', 'student_profile', 'household_profile',
            'admin_profile', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class StudentRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    university_id = serializers.CharField(required=True)
    university_name = serializers.CharField(required=True)

    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'password', 'first_name', 'last_name',
                  'phone_number', 'university_id', 'university_name']

    def validate_phone_number(self, value):
        if not value:
            return value
        # Students: phone number must be completely unique — no other user may have it
        if CustomUser.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError(
                "This phone number is already registered. Each user must have a unique phone number."
            )
        return value

    def create(self, validated_data):
        university_id = validated_data.pop('university_id')
        university_name = validated_data.pop('university_name')
        password = validated_data.pop('password')

        user = CustomUser.objects.create(role='STUDENT', **validated_data)
        user.set_password(password)
        user.save()

        # Update profile created by signal
        profile = user.student_profile
        profile.university_id = university_id
        profile.university_name = university_name
        profile.save()

        return user


class HouseholdRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    address = serializers.CharField(required=False, allow_blank=True)
    location_lat = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    location_lng = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)

    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'password', 'first_name', 'last_name',
                  'phone_number', 'address', 'location_lat', 'location_lng']

    def validate_phone_number(self, value):
        if not value:
            return value
        # Household owners may share a phone number only with other HOUSEHOLD accounts.
        # Block if the number is already used by a STUDENT or ADMIN.
        conflicting = CustomUser.objects.filter(phone_number=value).exclude(role='HOUSEHOLD')
        if conflicting.exists():
            raise serializers.ValidationError(
                "This phone number is already registered to a student or admin account."
            )
        return value

    def create(self, validated_data):
        address = validated_data.pop('address', '')
        location_lat = validated_data.pop('location_lat', None)
        location_lng = validated_data.pop('location_lng', None)
        password = validated_data.pop('password')

        user = CustomUser.objects.create(role='HOUSEHOLD', **validated_data)
        user.set_password(password)
        user.save()

        # Update profile created by signal
        profile = user.household_profile
        profile.address = address
        if location_lat is not None:
            profile.location_lat = location_lat
        if location_lng is not None:
            profile.location_lng = location_lng
        profile.save()

        return user
