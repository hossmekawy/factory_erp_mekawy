"""Fixtures for the cutting tests.

Everything builds on `make_lay`, which creates a lay that is already valid to
close: one detailed line whose arithmetic checks out, a size breakdown that
adds up, and a sheet image. Each test then breaks exactly the one thing it is
about.
"""
import datetime
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from devices.models import AttendanceLog, Device
from hr.models import Employee

from cutting.models import Bank, CuttingSettings, GarmentModel, Lay, LayLine, SizeSet

TODAY = datetime.date(2026, 8, 20)

# A 1x1 GIF — the smallest thing ImageField will accept as a sheet photo.
TINY_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!"
    b"\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


@pytest.fixture
def sheet_image():
    return SimpleUploadedFile("sheet.gif", TINY_GIF, content_type="image/gif")


@pytest.fixture
def settings_row(db):
    return CuttingSettings.get_solo()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="supervisor", password="x")


@pytest.fixture
def bank(db):
    return Bank.objects.create(code="B1", name="بنك ١")


@pytest.fixture
def leader(db):
    return Employee.objects.create(
        employee_code="101", full_name="محمد رئيس الفريق", is_team_leader=True
    )


@pytest.fixture
def size_set(db):
    return SizeSet.objects.create(name="كارل رجالي", sizes_raw="30 32 32 34 34 36")


@pytest.fixture
def garment_model(db, size_set):
    return GarmentModel.objects.create(
        code="1749", name="karl", category="men", fit="سليم", default_size_set=size_set
    )


@pytest.fixture
def device(db):
    return Device.objects.create(serial_number="ZK-TEST")


@pytest.fixture
def punch(db, device):
    """Record a punch for an employee code at a local date and time."""

    def _punch(employee_code, day, hour, minute=0):
        tz = timezone.get_current_timezone()
        ts = datetime.datetime.combine(day, datetime.time(hour, minute), tzinfo=tz)
        return AttendanceLog.objects.create(
            device=device, employee_code=employee_code, timestamp=ts
        )

    return _punch


@pytest.fixture
def make_lay(db, bank, garment_model, leader, user, size_set, sheet_image):
    """A closable lay. `lines` is a list of dicts overriding the default line."""
    from cutting import services

    def _make(
        lines=None,
        *,
        lay_length_m="4.95",
        sizes_raw=None,
        start_date=TODAY,
        end_date=None,
        entry_mode=Lay.MODE_DETAILED,
        with_sheet=True,
        **kwargs,
    ):
        # pieces_per_ply always comes from the size text, never set by hand —
        # the two disagreeing is exactly what V6 exists to catch.
        active_set = size_set
        if sizes_raw is not None:
            active_set = SizeSet.objects.create(name=f"طقم {sizes_raw}", sizes_raw=sizes_raw)

        lay = Lay.objects.create(
            start_date=start_date,
            end_date=end_date or start_date,
            bank=bank,
            garment_model=garment_model,
            size_set=active_set,
            team_leader=leader,
            entered_by=user,
            lay_width_cm=Decimal("167.00"),
            lay_length_m=Decimal(lay_length_m),
            pieces_per_ply=active_set.total_pieces,
            entry_mode=entry_mode,
            sheet_image=sheet_image if with_sheet else None,
            **kwargs,
        )
        services.sync_breakdown_from_size_set(lay)

        if lines is None:
            # 20 plies × 4.95 m + 0.50 m remnant = 99.50 m
            lines = [{"roll_length_m": "99.50", "plies": 20, "remnant_m": "0.50"}]
        for i, spec in enumerate(lines, start=1):
            LayLine.objects.create(
                lay=lay,
                line_no=spec.pop("line_no", i),
                roll_length_m=Decimal(str(spec.pop("roll_length_m"))),
                plies=spec.pop("plies"),
                remnant_m=Decimal(str(spec.pop("remnant_m", "0"))),
                **spec,
            )
        services.recalculate(lay)
        lay.refresh_from_db()
        return lay

    return _make


# --- API fixtures, shared by test_api.py and test_search.py ---------------

@pytest.fixture
def api():
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def make_user(db):
    from django.contrib.auth.models import Group

    def _make(role):
        u = User.objects.create_user(username=f"u_{role or 'none'}", password="pw")
        if role:
            u.groups.add(Group.objects.get_or_create(name=role)[0])
        return u

    return _make


@pytest.fixture
def as_role(api, make_user):
    def _login(role):
        api.force_authenticate(make_user(role))
        return api

    return _login


@pytest.fixture
def supervisor(as_role):
    return as_role("cutting_supervisor")
