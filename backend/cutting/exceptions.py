"""Turn model and service failures into one error shape the frontend can show.

Every rule that has a number in SRS 5.5 keeps that number all the way out to
the client, so the UI never has to match on message text:

    HTTP 400
    {
      "detail": "الفرشة مش جاهزة للقفل",
      "issues": [
        {"code": "V6", "level": "error",
         "message": "مجموع المقاسات (5) مش مطابق لعدد القطع في الراق (6)",
         "field": "size_breakdown", "line_no": null}
      ]
    }

The rules themselves live in the models and in services/validators, never in a
serializer — the admin and a shell session must hit exactly the same walls as
the API does.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError


def issue_dict(issue) -> dict:
    return {
        "code": issue.code,
        "level": issue.level,
        "message": issue.message,
        "field": issue.field or None,
        "line_no": issue.line_no,
    }


def issues_payload(issues, detail: str) -> dict:
    return {"detail": detail, "issues": [issue_dict(i) for i in issues]}


def django_errors_to_issues(exc: DjangoValidationError) -> list:
    """Flatten a model `clean()` failure, keeping the rule code Django carried.

    `LayLine.clean()` tags its errors with codes like "V3", so they survive the
    trip out to the client.
    """
    issues = []
    if hasattr(exc, "error_dict"):
        for field, errors in exc.error_dict.items():
            for err in errors:
                issues.append(
                    {
                        "code": getattr(err, "code", None) or "invalid",
                        "level": "error",
                        "message": err.message % (err.params or {}) if err.params else err.message,
                        "field": field if field != "__all__" else None,
                        "line_no": None,
                    }
                )
    else:
        for err in exc.error_list:
            issues.append(
                {
                    "code": getattr(err, "code", None) or "invalid",
                    "level": "error",
                    "message": err.message,
                    "field": None,
                    "line_no": None,
                }
            )
    return issues


def raise_as_drf(exc: DjangoValidationError, detail: str = "البيانات مش مظبوطة"):
    raise DRFValidationError({"detail": detail, "issues": django_errors_to_issues(exc)})
