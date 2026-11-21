"""
Firewall de circuitos y pre-validaciones espejo del motor Merqry.

Reglas inquebrantables:
  1. Solo se admite circuito_pago == 'IMSS_MERQRY'. Cualquier intento con
     ESPECIAL_CONTABILIDAD / EFECTIVO / OFF_IMSS se bloquea de forma dura.
  2. Lista negra dura contra 'Nomina Especial' (homonimo fiscal NOM.EX en Merqry
     que dispara BC/CFDI y AP.BAJA) y movimientos fuera de whitelist.
  3. Mapeo explicito por clave de empresa:
       PG 'BIO' -> Merqry (Empresa=1, Sucursal=1)
       PG 'NFA' -> Merqry (Empresa=2, Sucursal=2)
  4. Pre-validaciones espejo para cubrir el bug real de spNominaValidar
     (`vg_MovClase in ('NOM.N' 'NOM.EX')` sin coma) y cuadre contable 05005.
"""

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Tuple

ALLOWED_CIRCUIT = "IMSS_MERQRY"

FORBIDDEN_CIRCUITS = {
    "ESPECIAL_CONTABILIDAD",
    "EFECTIVO",
    "OFF_IMSS",
    "ESPECIAL",
}

FROZEN_READONLY_SCHEMAS = {
    "mq_bio_organicos_analisis",
}

EMPRESA_CLAVE_TO_MERQRY: Dict[str, Tuple[int, int]] = {
    "BIO": (1, 1),
    "NFA": (2, 2),
}

BLACKLISTED_MERQRY_MOVS_LOWER = {
    "nomina especial",
    "liquidacion",
    "finiquito",
    "aguinaldo",
    "ptu articulo 142",
    "ptu articulo 96",
    "ptu esp",
    "sdi",
}

WHITELISTED_MOVS_BY_MODULE: Dict[str, set[str]] = {
    "AP": {"Alta", "Baja", "Cambio", "ReIngreso"},
    "INCID": {
        "Faltas",
        "Falta Injustificada",
        "Falta Justificada",
        "Horas Extras",
        "Descanso Laborado",
        "Prima Dominical",
        "Incapacidad EG",
        "Incapacidad RT",
        "Incapacidad Mat",
        "Retardo Minutos",
        "Bono",
        "Compensacion",
    },
    "NOM": {"Nomina", "Nomina Quincenal"},
    "INV": {
        "Entrada",
        "Entrada Diversa",
        "Salida",
        "Consumo Materiales",
        "Transferencia",
        "Merma",
    },
    "CONT": {"Diario", "Egresos", "Ingresos"},
}

SAFE_INITIAL_STATUS_BY_MODULE: Dict[str, str] = {
    "AP": "SINAPLICAR",
    "INCID": "SINAPLICAR",
    "NOM": "PREVIO",
    "INV": "SINAPLICAR",
    "CONT": "SINAPLICAR",
}


class CircuitFirewallError(Exception):
    """Bloqueo duro de seguridad por circuito prohibido o movimiento en lista negra."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class MerqryPrevalidationError(Exception):
    """Error de pre-validacion funcional (espejo de SPs de Merqry)."""

    def __init__(self, merqry_code: str, message: str, detalles: List[Dict[str, Any]] | None = None):
        super().__init__(message)
        self.merqry_code = merqry_code
        self.message = message
        self.detalles = detalles or []


class MerqryWriteGateError(Exception):
    """Error de candado fail-closed (MERQRY_WRITE_ENABLED=false o entorno no autorizado)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def resolve_merqry_company(empresa_clave: str) -> Tuple[int, int]:
    clave = (empresa_clave or "").strip().upper()
    if clave not in EMPRESA_CLAVE_TO_MERQRY:
        raise CircuitFirewallError(
            "MERQRY_COMPANY_UNMAPPED",
            f"La clave de empresa '{empresa_clave}' no tiene mapeo autorizado en Merqry (solo BIO -> (1,1) y NFA -> (2,2)).",
        )
    return EMPRESA_CLAVE_TO_MERQRY[clave]


def enforce_circuit_and_mov_firewall(
    circuito_pago: str,
    modulo: str,
    merqry_mov: str,
) -> Tuple[str, str, str]:
    """Valida circuito IMSS_MERQRY y whitelist de modulo/movimiento."""
    circ = (circuito_pago or "").strip().upper()
    mod = (modulo or "").strip().upper()
    mov = (merqry_mov or "").strip()

    if circ in FORBIDDEN_CIRCUITS or circ != ALLOWED_CIRCUIT:
        raise CircuitFirewallError(
            "CIRCUIT_FIREWALL_BLOCKED",
            f"BLOQUEO DURO: circuito_pago='{circuito_pago}' rechazado. "
            "merqry_writer solo admite exclusivamente circuito 'IMSS_MERQRY' y nunca 'ESPECIAL_CONTABILIDAD'/efectivo.",
        )

    if mov.lower() in BLACKLISTED_MERQRY_MOVS_LOWER:
        raise CircuitFirewallError(
            "BLACKLISTED_MERQRY_MOV",
            f"BLOQUEO DURO: El movimiento Merqry '{mov}' esta en lista negra permanente "
            "(incluye 'Nomina Especial' fiscal NOM.EX que dispara BC/CFDI/AP.BAJA).",
        )

    if mod not in WHITELISTED_MOVS_BY_MODULE:
        raise CircuitFirewallError(
            "UNSUPPORTED_MERQRY_MODULE",
            f"Modulo '{modulo}' no autorizado para merqry_writer. Permitidos: {sorted(WHITELISTED_MOVS_BY_MODULE)}.",
        )

    if mov not in WHITELISTED_MOVS_BY_MODULE[mod]:
        raise CircuitFirewallError(
            "MOV_NOT_WHITELISTED",
            f"Movimiento '{mov}' no esta en la whitelist del modulo '{mod}'. "
            f"Permitidos: {sorted(WHITELISTED_MOVS_BY_MODULE[mod])}.",
        )

    return circ, mod, mov


def _parse_iso_date(val: Any, field_name: str) -> date:
    if isinstance(val, date):
        return val
    if isinstance(val, str) and val.strip():
        try:
            return date.fromisoformat(val.strip()[:10])
        except ValueError as exc:
            raise MerqryPrevalidationError("00120", f"Fecha invalida en '{field_name}': {val!r}.") from exc
    raise MerqryPrevalidationError("00120", f"Falta fecha obligatoria '{field_name}'.")


def _to_decimal(val: Any, field_name: str) -> Decimal:
    try:
        return Decimal(str(val))
    except Exception as exc:
        raise MerqryPrevalidationError("00120", f"Valor numerico invalido en '{field_name}': {val!r}.") from exc


def prevalidate_payload(modulo: str, merqry_mov: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pre-valida el payload contra las reglas reales de los SPs de Merqry
    (incluyendo las 4 validaciones omitidas por el bug de spNominaValidar).
    """
    if not isinstance(payload, dict):
        raise MerqryPrevalidationError("00120", "El payload debe ser un objeto JSON valido.")

    # Validar que ninguna partida interna declare circuito distinto de IMSS_MERQRY
    partidas = payload.get("partidas")
    if not isinstance(partidas, list) or len(partidas) == 0:
        raise MerqryPrevalidationError("00108", "No hay partidas que aplicar en el payload.")

    for idx, p in enumerate(partidas):
        if isinstance(p, dict) and p.get("circuito_pago"):
            p_circ = str(p["circuito_pago"]).strip().upper()
            if p_circ != ALLOWED_CIRCUIT:
                raise CircuitFirewallError(
                    "CIRCUIT_FIREWALL_BLOCKED",
                    f"BLOQUEO DURO en partida #{idx + 1}: circuito_pago='{p_circ}' distinto de 'IMSS_MERQRY'.",
                )

    if modulo == "AP":
        return _prevalidate_ap(merqry_mov, payload, partidas)
    if modulo == "INCID":
        return _prevalidate_incid(merqry_mov, payload, partidas)
    if modulo == "NOM":
        return _prevalidate_nom(merqry_mov, payload, partidas)
    if modulo == "INV":
        return _prevalidate_inv(merqry_mov, payload, partidas)
    if modulo == "CONT":
        return _prevalidate_cont(merqry_mov, payload, partidas)

    raise CircuitFirewallError("UNSUPPORTED_MERQRY_MODULE", f"Modulo no soportado: {modulo}")


def _prevalidate_ap(mov: str, payload: Dict[str, Any], partidas: List[Dict[str, Any]]) -> Dict[str, Any]:
    fecha_emision = _parse_iso_date(payload.get("fecha_emision"), "fecha_emision")
    moneda = (payload.get("moneda") or "").strip()
    if not moneda:
        raise MerqryPrevalidationError("00117", "Falta indicar la Moneda en cabecera AP.")

    required_fields = (
        "personal_sucursal",
        "departamento",
        "puesto",
        "tipo_nomina",
        "zona_economica",
        "periodo",
        "jornada",
        "tipo_contrato",
        "sueldo_diario",
        "tipo_dias",
    )
    for idx, p in enumerate(partidas):
        contacto = (p.get("contacto") or "").strip()
        if not contacto:
            raise MerqryPrevalidationError("08001", f"Partida #{idx + 1}: falta 'contacto' de personal.")
        if mov in {"Alta", "ReIngreso", "Cambio"}:
            jefe = (p.get("jefe_inmediato") or "").strip()
            if jefe and jefe == contacto:
                raise MerqryPrevalidationError("08005", f"Partida #{idx + 1}: jefe inmediato no puede ser el mismo empleado.")
            fecha_alta = _parse_iso_date(p.get("fecha_alta"), f"partidas[{idx}].fecha_alta")
            fecha_ant = _parse_iso_date(p.get("fecha_antiguedad"), f"partidas[{idx}].fecha_antiguedad")
            if fecha_ant > fecha_emision:
                raise MerqryPrevalidationError("08008", f"Partida #{idx + 1}: fecha_antiguedad posterior a fecha_emision.")
            if fecha_alta > fecha_emision:
                raise MerqryPrevalidationError("08009", f"Partida #{idx + 1}: fecha_alta posterior a fecha_emision.")
            missing = [f for f in required_fields if p.get(f) in (None, "")]
            if missing:
                raise MerqryPrevalidationError(
                    "08010",
                    f"Partida #{idx + 1}: faltan campos laborales obligatorios de spAPValidar: {', '.join(missing)}.",
                )
            if _to_decimal(p.get("sueldo_diario"), "sueldo_diario") <= 0:
                raise MerqryPrevalidationError("08017", f"Partida #{idx + 1}: sueldo_diario debe ser mayor a 0.")

    return {
        "modulo": "AP",
        "mov": mov,
        "partidas_count": len(partidas),
        "estatus_inicial_merqry": SAFE_INITIAL_STATUS_BY_MODULE["AP"],
    }


def _prevalidate_incid(mov: str, payload: Dict[str, Any], partidas: List[Dict[str, Any]]) -> Dict[str, Any]:
    _parse_iso_date(payload.get("fecha_emision"), "fecha_emision")
    if not (payload.get("moneda") or "").strip():
        raise MerqryPrevalidationError("00117", "Falta indicar la Moneda en cabecera INCID.")
    if payload.get("repetir") in (True, 1):
        if not payload.get("numero_veces") or int(payload["numero_veces"]) <= 0:
            raise MerqryPrevalidationError("10001", "Falta indicar numero_veces > 0 cuando repetir=1.")
        if not (payload.get("cuando") or "").strip():
            raise MerqryPrevalidationError("10002", "Falta indicar 'cuando' (Indistinto/Inicio Mes/Final Mes).")

    for idx, p in enumerate(partidas):
        if not (p.get("contacto") or "").strip():
            raise MerqryPrevalidationError("00120", f"Partida #{idx + 1}: falta 'contacto'.")
        _parse_iso_date(p.get("fecha_inicio"), f"partidas[{idx}].fecha_inicio")
        if mov in {"Bono", "Compensacion"}:
            if p.get("importe") is None or _to_decimal(p["importe"], "importe") <= 0:
                raise MerqryPrevalidationError("10004", f"Partida #{idx + 1}: falta importe > 0 para incidencia de percepcion.")
        else:
            if p.get("cantidad") is None or _to_decimal(p["cantidad"], "cantidad") <= 0:
                raise MerqryPrevalidationError("10003", f"Partida #{idx + 1}: falta cantidad > 0 para incidencia.")

    return {
        "modulo": "INCID",
        "mov": mov,
        "partidas_count": len(partidas),
        "estatus_inicial_merqry": SAFE_INITIAL_STATUS_BY_MODULE["INCID"],
    }


def _prevalidate_nom(mov: str, payload: Dict[str, Any], partidas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Replica exactamente las 4 validaciones que spNominaValidar omite por el bug
    `vg_MovClase in ('NOM.N' 'NOM.EX')` en MySQL 5.7:
      - 09001: formula_id obligatorio
      - 09017: fecha_pago obligatorio
      - 09002: aplicaciones_incid no exceden saldo/cantidad disponible
      - 09003: neto a pagar por empleado (SUM(P) - SUM(D)) >= 0
    """
    _parse_iso_date(payload.get("fecha_emision"), "fecha_emision")
    fecha_del = _parse_iso_date(payload.get("fecha_del"), "fecha_del")
    fecha_al = _parse_iso_date(payload.get("fecha_al"), "fecha_al")
    if fecha_al < fecha_del:
        raise MerqryPrevalidationError("00120", "fecha_al no puede ser menor a fecha_del.")

    if not (payload.get("moneda") or "").strip():
        raise MerqryPrevalidationError("00117", "Falta indicar la Moneda en cabecera NOM.")

    # Bug mirror #1: 09001 FormulaID
    if payload.get("formula_id") in (None, ""):
        raise MerqryPrevalidationError(
            "09001",
            "Falta indicar formula_id (validacion espejo obligatoria por bug de spNominaValidar).",
        )

    # Bug mirror #2: 09017 FechaPago
    if payload.get("fecha_pago") in (None, ""):
        raise MerqryPrevalidationError(
            "09017",
            "Falta capturar fecha_pago (validacion espejo obligatoria por bug de spNominaValidar).",
        )
    _parse_iso_date(payload.get("fecha_pago"), "fecha_pago")

    # Bug mirror #3: 09002 Aplicaciones de incidencias no exceden saldo/cantidad pendiente
    for idx, ap_inc in enumerate(payload.get("aplicaciones_incid") or []):
        disponible = _to_decimal(ap_inc.get("disponible", 0), f"aplicaciones_incid[{idx}].disponible")
        valor = _to_decimal(ap_inc.get("valor", 0), f"aplicaciones_incid[{idx}].valor")
        if disponible - valor < Decimal("0"):
            raise MerqryPrevalidationError(
                "09002",
                f"Excede la cantidad/importe disponible de incidencia para contacto '{ap_inc.get('contacto', '?')}' "
                f"(disponible={disponible}, valor={valor}).",
            )

    # Bug mirror #4: 09003 Neto a pagar por empleado >= 0
    neto_por_contacto: Dict[str, Decimal] = {}
    for idx, p in enumerate(partidas):
        contacto = (p.get("contacto") or "").strip()
        tipo = (p.get("tipo") or "").strip().upper()
        if not contacto:
            raise MerqryPrevalidationError("00120", f"Partida #{idx + 1}: falta 'contacto'.")
        if tipo not in {"P", "D"}:
            raise MerqryPrevalidationError("00120", f"Partida #{idx + 1}: tipo debe ser 'P' (Percepcion) o 'D' (Deduccion).")
        importe = _to_decimal(p.get("importe"), f"partidas[{idx}].importe")
        if importe < Decimal("0"):
            raise MerqryPrevalidationError("00120", f"Partida #{idx + 1}: importe no puede ser negativo.")
        neto_por_contacto.setdefault(contacto, Decimal("0"))
        neto_por_contacto[contacto] += importe if tipo == "P" else -importe

    negativos = [
        {"contacto": c, "neto": str(n)}
        for c, n in sorted(neto_por_contacto.items())
        if n < Decimal("0")
    ]
    if negativos:
        raise MerqryPrevalidationError(
            "09003",
            f"El importe neto a pagar no puede ser negativo (contactos: {[n['contacto'] for n in negativos]}).",
            detalles=negativos,
        )

    return {
        "modulo": "NOM",
        "mov": mov,
        "partidas_count": len(partidas),
        "empleados_count": len(neto_por_contacto),
        "total_neto_imss": str(sum(neto_por_contacto.values(), Decimal("0"))),
        "estatus_inicial_merqry": SAFE_INITIAL_STATUS_BY_MODULE["NOM"],
        "spNominaValidar_bug_guards_applied": ["09001", "09017", "09002", "09003"],
    }


def _prevalidate_inv(mov: str, payload: Dict[str, Any], partidas: List[Dict[str, Any]]) -> Dict[str, Any]:
    _parse_iso_date(payload.get("fecha_emision"), "fecha_emision")
    almacen = (payload.get("almacen") or "").strip()
    if not almacen:
        raise MerqryPrevalidationError("02010", "Falta indicar el Almacen en cabecera INV.")
    if mov == "Transferencia":
        almacen_destino = (payload.get("almacen_destino") or "").strip()
        if not almacen_destino:
            raise MerqryPrevalidationError("02012", "Falta indicar almacen_destino en Transferencia.")
        if almacen_destino == almacen:
            raise MerqryPrevalidationError("02013", "almacen y almacen_destino deben ser diferentes.")

    for idx, p in enumerate(partidas):
        if not (p.get("articulo") or "").strip():
            raise MerqryPrevalidationError("02001", f"Partida #{idx + 1}: falta 'articulo'.")
        cantidad = _to_decimal(p.get("cantidad"), f"partidas[{idx}].cantidad")
        if cantidad <= Decimal("0"):
            raise MerqryPrevalidationError("02002", f"Partida #{idx + 1}: cantidad debe ser > 0.")
        if not (p.get("unidad") or "").strip():
            raise MerqryPrevalidationError("02047", f"Partida #{idx + 1}: falta 'unidad'.")
        costo = _to_decimal(p.get("costo", 0), f"partidas[{idx}].costo")
        if costo < Decimal("0"):
            raise MerqryPrevalidationError("02009", f"Partida #{idx + 1}: costo no puede ser negativo.")
        series_lotes = p.get("series_lotes")
        if series_lotes is not None:
            if not isinstance(series_lotes, list) or not series_lotes:
                raise MerqryPrevalidationError("02017", f"Partida #{idx + 1}: series_lotes vacio.")
            suma_lotes = sum(
                (_to_decimal(sl.get("cantidad"), "series_lotes.cantidad") for sl in series_lotes),
                Decimal("0"),
            )
            if suma_lotes != cantidad:
                raise MerqryPrevalidationError(
                    "02017",
                    f"Partida #{idx + 1}: suma de series_lotes ({suma_lotes}) difiere de cantidad ({cantidad}).",
                )

    return {
        "modulo": "INV",
        "mov": mov,
        "almacen": almacen,
        "partidas_count": len(partidas),
        "estatus_inicial_merqry": SAFE_INITIAL_STATUS_BY_MODULE["INV"],
    }


def _prevalidate_cont(mov: str, payload: Dict[str, Any], partidas: List[Dict[str, Any]]) -> Dict[str, Any]:
    _parse_iso_date(payload.get("fecha_emision"), "fecha_emision")
    moneda = (payload.get("moneda") or "").strip()
    if moneda != "Pesos":
        raise MerqryPrevalidationError(
            "05003",
            f"La Moneda de la poliza ('{moneda}') debe coincidir con MonedaOmision='Pesos'.",
        )

    total_cargos = Decimal("0")
    total_abonos = Decimal("0")
    for idx, p in enumerate(partidas):
        if not (p.get("cuenta") or "").strip():
            raise MerqryPrevalidationError("05000", f"Partida #{idx + 1}: falta 'cuenta' contable.")
        cargo = _to_decimal(p.get("cargo", 0), f"partidas[{idx}].cargo")
        abono = _to_decimal(p.get("abono", 0), f"partidas[{idx}].abono")
        if cargo < Decimal("0") or abono < Decimal("0"):
            raise MerqryPrevalidationError("00120", f"Partida #{idx + 1}: cargo/abono no pueden ser negativos.")
        if cargo == Decimal("0") and abono == Decimal("0"):
            raise MerqryPrevalidationError("00120", f"Partida #{idx + 1}: debe indicar cargo o abono > 0.")
        total_cargos += cargo
        total_abonos += abono

    if total_cargos.quantize(Decimal("0.01")) != total_abonos.quantize(Decimal("0.01")):
        raise MerqryPrevalidationError(
            "05005",
            f"La suma de Cargos ({total_cargos}) y Abonos ({total_abonos}) es diferente.",
        )

    return {
        "modulo": "CONT",
        "mov": mov,
        "partidas_count": len(partidas),
        "total_cargos": str(total_cargos.quantize(Decimal("0.01"))),
        "total_abonos": str(total_abonos.quantize(Decimal("0.01"))),
        "estatus_inicial_merqry": SAFE_INITIAL_STATUS_BY_MODULE["CONT"],
    }
