import re

from app.core.config import settings


class MerqryReadOnlyViolationError(RuntimeError):
    """Error critico al intentar cualquier escritura o migracion contra Merqry."""


_FORBIDDEN_SQL_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|REPLACE|MERGE|GRANT|REVOKE|CALL|EXEC|LOCK|UNLOCK)\b",
    re.IGNORECASE,
)


def assert_merqry_readonly_sql(sql: str) -> str:
    """
    Guarda estricta SOLO LECTURA para cualquier consulta dirigida al espejo MySQL de Merqry.
    Rechaza cualquier verbo de escritura, DDL o sentencias multiples encadenadas.
    """
    if not settings.merqry_readonly_mode:
        raise MerqryReadOnlyViolationError(
            "MERQRY_READONLY_MODE debe estar en True en todo momento."
        )
    cleaned = sql.strip()
    if not cleaned:
        raise MerqryReadOnlyViolationError("Consulta SQL vacía rechazada.")
    # Eliminar punto y coma final opcional, pero prohibir sentencias encadenadas
    without_trailing = cleaned[:-1].strip() if cleaned.endswith(";") else cleaned
    if ";" in without_trailing:
        raise MerqryReadOnlyViolationError(
            "Prohibido encadenar múltiples sentencias SQL contra Merqry."
        )
    upper = without_trailing.upper()
    if not (upper.startswith("SELECT ") or upper.startswith("SHOW ") or upper.startswith("DESCRIBE ")):
        raise MerqryReadOnlyViolationError(
            "Merqry solo admite consultas SELECT/SHOW/DESCRIBE (modo estrictamente SOLO LECTURA)."
        )
    if _FORBIDDEN_SQL_PATTERN.search(without_trailing):
        raise MerqryReadOnlyViolationError(
            "Operación de escritura o DDL detectada y bloqueada contra Merqry."
        )
    return without_trailing
