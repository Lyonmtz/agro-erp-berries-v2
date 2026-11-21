from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict

# Salario Minimo General 2026 de referencia (configurable en parametrizacion futura)
SMG_2026_REF = Decimal("315.04")


def _r2(val: Decimal) -> Decimal:
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def dias_vacaciones_lft_por_anio(anios_cumplidos: int) -> int:
    """Tabla LFT vigente (Vacaciones Dignas): 12 dias anio 1, +2 hasta anio 5, +2 cada 5 anios."""
    if anios_cumplidos <= 1:
        return 12
    if anios_cumplidos == 2:
        return 14
    if anios_cumplidos == 3:
        return 16
    if anios_cumplidos == 4:
        return 18
    if anios_cumplidos == 5:
        return 20
    tramos = (anios_cumplidos - 1) // 5
    return 20 + (tramos * 2)


def calcular_finiquito_lft_2026(
    *,
    fecha_ingreso: date,
    fecha_baja: date,
    salario_diario: Decimal,
    motivo_baja: str,
    dias_salarios_pendientes: Decimal = Decimal("0"),
    deducciones_autorizadas: Decimal = Decimal("0"),
    smg_referencia: Decimal = SMG_2026_REF,
) -> Dict[str, Decimal | int | str]:
    if fecha_baja < fecha_ingreso:
        raise ValueError("fecha_baja no puede ser anterior a fecha_ingreso.")

    # Dias trabajados en el anio calendario de la baja (para aguinaldo)
    inicio_anio = date(fecha_baja.year, 1, 1)
    inicio_aguinaldo = max(fecha_ingreso, inicio_anio)
    dias_trabajados_anio = (fecha_baja - inicio_aguinaldo).days + 1

    # Antiguedad total en dias y anios
    dias_totales = (fecha_baja - fecha_ingreso).days + 1
    anios_servicio = Decimal(dias_totales) / Decimal("365")
    anio_vacacional = max(1, int(anios_servicio) + 1)

    # Dias trabajados desde el ultimo aniversario (para vacaciones proporcionales)
    dias_en_anio_aniversario = dias_totales % 365
    if dias_en_anio_aniversario == 0 and dias_totales > 0:
        dias_en_anio_aniversario = 365

    dias_vac_anuales = Decimal(dias_vacaciones_lft_por_anio(anio_vacacional))

    aguinaldo = _r2(
        (Decimal("15") * Decimal(dias_trabajados_anio) / Decimal("365")) * salario_diario
    )
    vacaciones = _r2(
        (dias_vac_anuales * Decimal(dias_en_anio_aniversario) / Decimal("365")) * salario_diario
    )
    prima_vacacional = _r2(vacaciones * Decimal("0.25"))
    salarios_pend = _r2(dias_salarios_pendientes * salario_diario)

    # Prima de antiguedad (12 dias/anio, salario topado a 2x SMG) en despido o >= 15 anios
    aplica_prima_ant = motivo_baja in ("DESPIDO_JUSTIFICADO", "DESPIDO_INJUSTIFICADO") or anios_servicio >= Decimal("15")
    if aplica_prima_ant:
        salario_tope = min(salario_diario, smg_referencia * Decimal("2"))
        prima_antiguedad = _r2(Decimal("12") * anios_servicio * salario_tope)
    else:
        prima_antiguedad = Decimal("0.00")

    # Indemnizacion constitucional (90 dias) solo en despido injustificado
    if motivo_baja == "DESPIDO_INJUSTIFICADO":
        indemnizacion = _r2(Decimal("90") * salario_diario)
    else:
        indemnizacion = Decimal("0.00")

    ded = _r2(deducciones_autorizadas)
    total_neto = _r2(
        aguinaldo
        + vacaciones
        + prima_vacacional
        + salarios_pend
        + prima_antiguedad
        + indemnizacion
        - ded
    )

    return {
        "dias_trabajados_anio": dias_trabajados_anio,
        "dias_vacaciones_tabla": int(dias_vac_anuales),
        "aguinaldo_proporcional": aguinaldo,
        "vacaciones_proporcionales": vacaciones,
        "prima_vacacional": prima_vacacional,
        "salarios_pendientes": salarios_pend,
        "prima_antiguedad": prima_antiguedad,
        "indemnizacion_constitucional": indemnizacion,
        "deducciones_autorizadas": ded,
        "total_neto_finiquito": total_neto,
    }
