"""ZKTeco ADMS / PUSH protocol endpoints (/iclock/*).

The device initiates every request (works from behind the factory NAT):
  GET  /iclock/cdata?SN=..&options=all   handshake, server returns config
  POST /iclock/cdata?SN=..&table=ATTLOG  punch records
  POST /iclock/cdata?SN=..&table=OPERLOG user/fingerprint/operation records
  GET  /iclock/getrequest?SN=..          poll for queued commands
  POST /iclock/devicecmd?SN=..           results of executed commands

Responses are plain text. No JWT here — the device can't authenticate;
requests are matched to Device rows by serial number.
"""
import base64
import logging
from datetime import datetime, timedelta

from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

# How long after a wipe request we keep dropping incoming pushes, in case the
# device never confirms CLEAR DATA (so the guard can't get stuck forever).
WIPE_WINDOW = timedelta(minutes=15)


def _is_wiping(device) -> bool:
    return bool(
        device.wipe_requested_at
        and device.wipe_requested_at >= timezone.now() - WIPE_WINDOW
    )

from hr.models import Employee
from .models import AttendanceLog, Device, DeviceCommand, FingerprintTemplate
from . import services

logger = logging.getLogger("iclock")


def _text(body: str) -> HttpResponse:
    return HttpResponse(body, content_type="text/plain")


def _get_device(request):
    sn = request.GET.get("SN", "").strip()
    if not sn:
        return None
    device, created = Device.objects.get_or_create(
        serial_number=sn, defaults={"name": "جهاز البصمة"}
    )
    if created:
        logger.info("New device registered: %s", sn)
    device.last_seen = timezone.now()
    device.save(update_fields=["last_seen"])
    return device


def _parse_ts(value: str):
    """Device sends naive local (Cairo) time: '2026-07-09 08:01:23'."""
    dt = datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S")
    return timezone.make_aware(dt)


def _parse_kv_line(line: str) -> dict:
    """Parse 'PIN=1\\tName=Ali\\t...' into a dict (keys lowercased)."""
    out = {}
    for part in line.split("\t"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip().lower()] = v.strip()
    return out


def _handle_attlog(device, body: str) -> int:
    count = 0
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        fields = line.split("\t")
        if len(fields) < 2:
            continue
        code = fields[0].strip()
        try:
            ts = _parse_ts(fields[1])
        except ValueError:
            logger.warning("Bad ATTLOG line: %r", line)
            continue
        punch_state = int(fields[2]) if len(fields) > 2 and fields[2].isdigit() else 0
        verify_type = int(fields[3]) if len(fields) > 3 and fields[3].isdigit() else 1
        employee = Employee.objects.filter(employee_code=code).first()
        _, created = AttendanceLog.objects.get_or_create(
            device=device,
            employee_code=code,
            timestamp=ts,
            defaults={
                "employee": employee,
                "punch_state": punch_state,
                "verify_type": verify_type,
            },
        )
        if created:
            count += 1
    return count


def _store_fingerprint(kv: dict):
    code = kv.get("pin")
    fid = kv.get("fid", kv.get("index", "0"))
    tmp = kv.get("tmp")
    if not code or tmp is None:
        return
    FingerprintTemplate.objects.update_or_create(
        employee_code=code,
        finger_id=int(fid),
        defaults={"template": tmp, "valid": int(kv.get("valid", "1") or 1)},
    )


def _handle_operlog(device, body: str) -> int:
    """USER / FP lines: keep employees and fingerprint backups in sync."""
    count = 0
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            if line.upper().startswith("USER "):
                kv = _parse_kv_line(line[5:])
                code = kv.get("pin")
                if not code:
                    continue
                Employee.objects.get_or_create(
                    employee_code=code,
                    defaults={"full_name": kv.get("name") or f"موظف {code}"},
                )
                count += 1
            elif line.upper().startswith("FP "):
                _store_fingerprint(_parse_kv_line(line[3:]))
                count += 1
            else:
                # OPLOG and other operation records: acknowledged, not stored.
                count += 1
        except Exception:
            logger.exception("Failed OPERLOG line: %r", line)
    return count


def _handle_biodata(device, body: str) -> int:
    """Newer firmwares push fingerprints as BIODATA (Type=1) lines."""
    count = 0
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.upper().startswith("BIODATA "):
            line = line[8:]
        kv = _parse_kv_line(line.replace("&", "\t"))
        if kv.get("type", "1") == "1" and kv.get("tmp"):
            kv.setdefault("fid", kv.get("no", kv.get("index", "0")))
            _store_fingerprint(kv)
            count += 1
    return count


@csrf_exempt
def cdata(request):
    device = _get_device(request)
    if device is None:
        return _text("ERROR: SN missing")

    if request.method == "GET":
        # Handshake: tell the device what to push and how often.
        config = (
            f"GET OPTION FROM: {device.serial_number}\n"
            "ATTLOGStamp=None\n"
            "OPERLOGStamp=None\n"
            "ATTPHOTOStamp=None\n"
            "ErrorDelay=30\n"
            "Delay=3\n"
            "TransTimes=00:00;12:00\n"
            "TransInterval=1\n"
            "TransFlag=TransData AttLog OpLog EnrollUser ChgUser EnrollFP ChgFP FPImag UserPic\n"
            "TimeZone=3\n"
            "Realtime=1\n"
            "Encrypt=None\n"
        )
        if request.GET.get("options"):
            device.options_raw = request.META.get("QUERY_STRING", "")
            device.push_version = request.GET.get("pushver", "")
            device.save(update_fields=["options_raw", "push_version"])
        return _text(config)

    # During a wipe, drop whatever the device is still pushing so it can't
    # re-populate the freshly cleared database before CLEAR DATA lands.
    if _is_wiping(device):
        return _text("OK: 0")

    body = request.body.decode("utf-8", errors="replace")
    table = request.GET.get("table", "").upper()
    if table == "ATTLOG":
        n = _handle_attlog(device, body)
    elif table == "OPERLOG":
        n = _handle_operlog(device, body)
    elif table == "BIODATA":
        n = _handle_biodata(device, body)
    else:
        logger.info("Unhandled table %s from %s: %.200r", table, device.serial_number, body)
        n = len([l for l in body.splitlines() if l.strip()])
    return _text(f"OK: {n}")


@csrf_exempt
def getrequest(request):
    device = _get_device(request)
    if device is None:
        return _text("ERROR: SN missing")
    return _text(services.pop_pending_commands(device))


@csrf_exempt
def devicecmd(request):
    device = _get_device(request)
    if device is None:
        return _text("ERROR: SN missing")
    body = request.body.decode("utf-8", errors="replace")
    # Body: 'ID=12&Return=0&CMD=DATA' — possibly several results separated by newlines.
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        kv = {}
        for part in line.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                kv[k.strip().lower()] = v.strip()
        cmd_id = kv.get("id")
        if not cmd_id or not cmd_id.isdigit():
            continue
        ret = kv.get("return", "")
        cmd = DeviceCommand.objects.filter(id=int(cmd_id), device=device).first()
        if not cmd:
            continue
        cmd.status = "done" if ret in ("0", "") else "failed"
        cmd.return_code = ret
        cmd.finished_at = timezone.now()
        cmd.save(update_fields=["status", "return_code", "finished_at"])
        # The wipe is complete the moment the device confirms CLEAR DATA:
        # lift the guard so real punches start flowing again.
        if cmd.status == "done" and cmd.command.strip().upper().startswith("CLEAR DATA"):
            device.wipe_requested_at = None
            device.save(update_fields=["wipe_requested_at"])
    return _text("OK")


@csrf_exempt
def ping(request):
    if request.GET.get("SN"):
        _get_device(request)
    return _text("OK")
