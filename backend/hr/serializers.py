from django.contrib.auth.models import Group, User
from rest_framework import serializers

from devices.models import FingerprintTemplate
from .models import Department, Employee, SiteSettings, WorkSchedule
from .permissions import ROLE_ORDER, role_of


class DepartmentSerializer(serializers.ModelSerializer):
    employee_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Department
        fields = ["id", "name", "employee_count"]


class EmployeeSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)
    fingerprint_count = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = [
            "id", "employee_code", "full_name", "department", "department_name",
            "job_title", "national_id", "phone_number", "address", "gender",
            "birth_date", "hire_date", "salary", "photo", "id_front_image",
            "id_back_image", "is_active", "fingerprint_count", "created_at",
        ]

    def get_fingerprint_count(self, obj):
        return FingerprintTemplate.objects.filter(
            employee_code=obj.employee_code, valid=1
        ).count()


class FingerprintSerializer(serializers.ModelSerializer):
    class Meta:
        model = FingerprintTemplate
        fields = ["id", "employee_code", "finger_id", "valid", "updated_at"]


class WorkScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkSchedule
        fields = ["id", "work_start", "work_end", "weekend_days"]


class SystemUserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    password = serializers.CharField(write_only=True, required=False, min_length=6)
    role_input = serializers.ChoiceField(
        choices=ROLE_ORDER, write_only=True, required=False, source="role_in"
    )

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "is_active", "role", "password", "role_input"]

    def get_role(self, obj):
        return role_of(obj)

    def _apply_role(self, user, role):
        if role:
            user.groups.clear()
            user.groups.add(Group.objects.get_or_create(name=role)[0])

    def create(self, validated_data):
        role = validated_data.pop("role_in", "hr")
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        user.save()
        self._apply_role(user, role)
        return user

    def update(self, instance, validated_data):
        role = validated_data.pop("role_in", None)
        password = validated_data.pop("password", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        if password:
            instance.set_password(password)
        instance.save()
        self._apply_role(instance, role)
        return instance
