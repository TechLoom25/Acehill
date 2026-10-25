"""SMS delivery. Swap send_sms for any provider."""
import logging
import re

from config import AT_API_KEY, AT_SENDER_ID, AT_USERNAME

log = logging.getLogger("acehill.sms")
_initialised = False

# Africa's Talking per-recipient status codes that mean "accepted": Processed, Sent, Queued.
_ACCEPTED = {100, 101, 102}


class SmsError(Exception):
    """The provider accepted none of the recipients."""


def normalise_phone(raw: str) -> str:
    """Return +<country><number>. Bare Kenyan numbers (07.., 01.., 7..) are assumed to be +254."""
    digits = re.sub(r"[\s\-().]", "", raw)
    if digits.startswith("+"):
        result = digits
    elif digits.startswith("254"):
        result = "+" + digits
    elif digits.startswith("0") and len(digits) == 10:
        result = "+254" + digits[1:]
    elif len(digits) == 9 and digits[0] in "71":
        result = "+254" + digits
    else:
        result = digits
    if not re.fullmatch(r"\+\d{9,15}", result):
        raise ValueError("Enter a valid phone number, e.g. 0712345678 or +254712345678")
    return result


def send_sms(phones: list[str], message: str) -> int:
    """Send a message and return how many recipients the provider accepted.

    Prints to the console when AT_API_KEY is unset. Raises SmsError if nobody was accepted.
    """
    global _initialised
    if not AT_API_KEY:
        print(f"[SMS stub] to={phones} msg={message}")
        return len(phones)

    import africastalking

    if not _initialised:
        africastalking.initialize(AT_USERNAME, AT_API_KEY)
        _initialised = True
    kwargs = {"sender_id": AT_SENDER_ID} if AT_SENDER_ID else {}
    response = africastalking.SMS.send(message, phones, **kwargs)

    data = response.get("SMSMessageData", {})
    recipients = data.get("Recipients", [])
    accepted = [r for r in recipients if r.get("statusCode") in _ACCEPTED]
    for r in recipients:
        if r.get("statusCode") not in _ACCEPTED:
            log.warning("SMS to %s rejected: %s", r.get("number"), r.get("status"))
    if not accepted:
        raise SmsError(data.get("Message") or "The provider accepted no recipients")
    return len(accepted)


def try_send_sms(phones: list[str], message: str) -> bool:
    """Best-effort send: a provider outage must not fail the repair workflow."""
    try:
        return send_sms(phones, message) > 0
    except Exception:  # noqa: BLE001 - provider SDKs raise anything
        log.exception("SMS delivery failed")
        return False
