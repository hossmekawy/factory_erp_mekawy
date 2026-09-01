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

Three backends, picked in this order by what is configured — a box with none
of them still runs the digest, printing it to the log rather than crashing.

### Resend (what this install uses)

```
RESEND_API_KEY=re_...
DEFAULT_FROM_EMAIL=onboarding@resend.dev
```

`onboarding@resend.dev` is Resend's shared test sender: until a domain is
verified in the Resend dashboard it will only deliver to the address that owns
the account. To send to anyone else, verify a domain and set
`DEFAULT_FROM_EMAIL` to an address on it.

### SMTP (if you ever move off Resend)

```
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=...
EMAIL_HOST_PASSWORD=...
EMAIL_USE_TLS=True
```

### Who receives it

Each alert is written per person, but the digest groups by **address**, not by
person, and lists each lay once per address. Several accounts sharing one
inbox therefore get one email, not one each.

Addresses come from each user's own `email` field plus
`CuttingSettings.notify_emails` (comma separated) — which is how a small
install where nobody has set an email address still gets its alerts somewhere.
