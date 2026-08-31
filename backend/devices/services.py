"""Builders for commands queued to ZKTeco devices via the PUSH protocol.

Commands are stored in DeviceCommand and delivered when the device polls
GET /iclock/getrequest. Line format on the wire: ``C:<id>:<command>``.
"""
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from .models import Device, DeviceCommand

TAB = "\t"

# Re-send a command the device hasn't confirmed after this long (it may have
# missed the reply, rebooted, or been busy uploading a data backlog).
RETRY_AFTER = timedelta(seconds=45)
MAX_DELIVERIES = 3


def queue(device: Device, command: str, description: str = "") -> DeviceCommand:
    return DeviceCommand.objects.create(
        device=device, command=command, description=description
    )


def queue_for_all(command: str, description: str = ""):
    return [
        queue(d, command, description)
        for d in Device.objects.filter(is_active=True)
    ]


def update_user(device: Device, employee) -> DeviceCommand:
    cmd = (
        f"DATA UPDATE USERINFO PIN={employee.employee_code}"
        f"{TAB}Name={employee.full_name[:24]}"
        f"{TAB}Pri=0{TAB}Passwd={TAB}Card={TAB}Grp=1{TAB}TZ="
    )
    return queue(device, cmd, f"إرسال بيانات الموظف {employee.full_name} للجهاز")


def delete_user(device: Device, employee_code: str) -> DeviceCommand:
    return queue(
        device,
        f"DATA DELETE USERINFO PIN={employee_code}",
        f"حذف الموظف {employee_code} من الجهاز",
    )


def enroll_fingerprint(device: Device, employee_code: str, finger_id: int) -> DeviceCommand:
    cmd = (
        f"ENROLL_FP PIN={employee_code}{TAB}FID={finger_id}"
        f"{TAB}RETRY=3{TAB}OVERWRITE=1"
    )
    return queue(device, cmd, f"تسجيل بصمة جديدة للموظف {employee_code} (إصبع {finger_id})")


def push_fingerprint(device: Device, fp) -> DeviceCommand:
    cmd = (
        f"DATA UPDATE FINGERTMP PIN={fp.employee_code}{TAB}FID={fp.finger_id}"
        f"{TAB}Size={len(fp.template)}{TAB}Valid={fp.valid}{TAB}TMP={fp.template}"
    )
    return queue(device, cmd, f"إرسال بصمة {fp.employee_code}/{fp.finger_id} للجهاز")


def check_data(device: Device) -> DeviceCommand:
    return queue(device, "CHECK", "مزامنة البيانات من الجهاز")


def reboot(device: Device) -> DeviceCommand:
    return queue(device, "REBOOT", "إعادة تشغيل الجهاز")


def clear_all_data(device: Device) -> DeviceCommand:
    """Wipe every user, fingerprint, face and attendance record on the device."""
    return queue(device, "CLEAR DATA", "مسح كل بيانات الجهاز")


def clear_attendance(device: Device) -> DeviceCommand:
    return queue(device, "CLEAR LOG", "مسح سجلات الحضور من الجهاز")


def pop_pending_commands(device: Device) -> str:
    """Return the single next command as a protocol line and mark it sent.

    One command per poll is the reliable pattern: many firmwares only act on
    the first line of a getrequest reply. Commands the device never confirms
    are re-sent (up to MAX_DELIVERIES) then marked failed so they don't loop
    forever.
    """
    now = timezone.now()
    candidates = (
        DeviceCommand.objects.filter(device=device)
        .filter(Q(status="pending") | Q(status="sent", sent_at__lt=now - RETRY_AFTER))
        .order_by("created_at")
    )
    for cmd in candidates:
        if cmd.delivery_count >= MAX_DELIVERIES:
            cmd.status = "failed"
            cmd.finished_at = now
            cmd.save(update_fields=["status", "finished_at"])
            continue
        cmd.status = "sent"
        cmd.sent_at = now
        cmd.delivery_count += 1
        cmd.save(update_fields=["status", "sent_at", "delivery_count"])
        return f"C:{cmd.id}:{cmd.command}\n"
    return "OK"
