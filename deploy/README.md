# Deployment bits

## Daily cutting digest (SRS 11.1)

SRS 11.1 names Celery or django-q. Neither is installed, and neither earns its
keep for a job that runs once a day: a queue exists for work that must happen
soon and may fail, not for a scheduled digest. This is a management command on
a systemd timer, which is what the box already runs everything else with.

```sh
cp deploy/factory-erp-cutting-digest.* /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now factory-erp-cutting-digest.timer
systemctl list-timers factory-erp-cutting-digest.timer   # confirm it is armed
```

Run it by hand to check:

```sh
cd backend && venv/bin/python manage.py send_cutting_digest --dry-run
```

## Email

Unconfigured, Django prints the digest to the log instead of sending it, so a
box with no SMTP still runs without crashing. To send for real, add to
`backend/.env`:

```
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=...
EMAIL_HOST_PASSWORD=...
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=erp@mekawyerp.shop
```

Extra recipients beyond each user's own address go in
`CuttingSettings.notify_emails`, comma separated.
