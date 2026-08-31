"""Attendance derived from raw punches, callable for one employee over a period.

The punch→hours rule lives here: per employee per calendar day the first punch
is check-in, the last is check-out, and hours is the span between them. A day
with a single punch yields **zero hours** — the man worked, he just never
punched out — so those days are reported separately and excluded from any
average or rate. See `PeriodHours.coverage_pct`.

Everything joins on `employee_code`, never on `AttendanceLog.employee`: 17% of
the live rows have a null FK while the code is always populated.
"""
import datetime
from collections import defaultdict
from dataclasses import dataclass, field

from django.db.models import Min
from django.utils import timezone

from devices.models import AttendanceLog

# Below this, a productivity figure built on the period is not worth trusting.
RELIABLE_COVERAGE_PCT = 50.0


@dataclass
class DayHours:
    date: datetime.date
    first_punch: datetime.datetime
    last_punch: datetime.datetime
    hours: float  # 0.0 when the day holds a single punch

    @property
    def is_measurable(self) -> bool:
        return self.hours > 0


@dataclass
class PeriodHours:
    """Hours for one employee across a date range, with its own reliability."""

    employee_code: str
    start: datetime.date
    end: datetime.date
    days: list = field(default_factory=list)  # [DayHours] ordered by date

    @property
    def total_days(self) -> int:
        """Calendar days in the requested period, both ends included."""
        return (self.end - self.start).days + 1

    @property
    def days_present(self) -> int:
        """Days with at least one punch."""
        return len(self.days)

    @property
    def measured_days(self) -> int:
        """Days that produced real hours (two punches or more)."""
        return sum(1 for d in self.days if d.is_measurable)

    @property
    def total_hours(self) -> float:
        return round(sum(d.hours for d in self.days), 2)

    @property
    def coverage_pct(self) -> float:
        """Share of the period we actually have hours for."""
        if not self.total_days:
            return 0.0
        return round(self.measured_days / self.total_days * 100, 1)

    @property
    def is_reliable(self) -> bool:
        return self.measured_days > 0 and self.coverage_pct >= RELIABLE_COVERAGE_PCT

    @property
    def coverage_label(self) -> str:
        return f"مبني على {self.measured_days} يوم من أصل {self.total_days}"


def _day_bounds(start: datetime.date, end: datetime.date):
    tz = timezone.get_current_timezone()
    return (
        datetime.datetime.combine(start, datetime.time.min, tzinfo=tz),
        datetime.datetime.combine(end + datetime.timedelta(days=1), datetime.time.min, tzinfo=tz),
    )


def attendance_data_start():
    """Date of the earliest punch on record, or None when there are no punches.

    Attendance history does not reach back forever, so a lay older than this is
    unverifiable rather than absent — callers skip the presence check silently.
    """
    earliest = AttendanceLog.objects.aggregate(first=Min("timestamp"))["first"]
    return timezone.localtime(earliest).date() if earliest else None


def punches_by_day(start: datetime.date, end: datetime.date, codes=None) -> dict:
    """(employee_code, local date) -> sorted [datetime], for the whole period."""
    range_start, range_end = _day_bounds(start, end)
    qs = AttendanceLog.objects.filter(timestamp__gte=range_start, timestamp__lt=range_end)
    if codes is not None:
        qs = qs.filter(employee_code__in=list(codes))

    grouped = defaultdict(list)
    for code, ts in qs.values_list("employee_code", "timestamp"):
        local = timezone.localtime(ts)
        grouped[(code, local.date())].append(local)
    for times in grouped.values():
        times.sort()
    return dict(grouped)


def present_codes(start: datetime.date, end: datetime.date) -> set:
    """Employee codes with at least one punch on any day in the range."""
    range_start, range_end = _day_bounds(start, end)
    return set(
        AttendanceLog.objects.filter(
            timestamp__gte=range_start, timestamp__lt=range_end
        ).values_list("employee_code", flat=True)
    )


def hours_for(employee_code: str, start: datetime.date, end: datetime.date) -> PeriodHours:
    """Per-day hours for one employee over an inclusive date range."""
    grouped = punches_by_day(start, end, codes=[employee_code])
    days = []
    for (_code, day), times in sorted(grouped.items(), key=lambda kv: kv[0][1]):
        first, last = times[0], times[-1]
        hours = round((last - first).total_seconds() / 3600, 2) if last > first else 0.0
        days.append(DayHours(date=day, first_punch=first, last_punch=last, hours=hours))
    return PeriodHours(employee_code=employee_code, start=start, end=end, days=days)
