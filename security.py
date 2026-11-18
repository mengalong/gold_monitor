import re
from collections.abc import Iterable


_SENSITIVE_QUERY_PARAMETER = re.compile(
    r"(?i)((?:^|[?&])(?:api[_-]?key|access[_-]?token|token|secret|password)=)[^&\s]+"
)


def redact_secrets(value: object, secrets: Iterable[str] = ()) -> str:
    """Remove known secrets and sensitive URL query parameters from text."""
    text = str(value)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return _SENSITIVE_QUERY_PARAMETER.sub(r"\1***", text)
