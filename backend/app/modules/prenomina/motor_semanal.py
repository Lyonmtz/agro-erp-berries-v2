from decimal import Decimal, ROUND_HALF_UP
from typing import Dict


def _r2(val: Decimal) -> Decimal:
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calcular_prenomina_trabajador_semanal(
    *,
    cajas_ls: Decimal,
    cajas_domingo: Decimal,
    cajas_merma: Decimal,
    dias_trabajados: int,
    tarifa_caja_ls: Decimal = Decimal("28.00"),
    domingo_umbral_cajas: Decimal = Decimal("10.00"),
    domingo_tarifa_base: Decimal = Decimal("28.00"),
    domingo_tarifa_excedente: Decimal = Decimal("40.00"),
    minimo_semanal_garantizado: Decimal = Decimal("2350.00"),
    dias_minimos_para_garantia: int = 1,
    alerta_merma_pct: Decimal = Decimal("7.00"),
) -> Dict[str, Decimal | bool]:
    """
    Motor semanal configurable SEAH:
      - Lunes a Sabado: cajas_ls * tarifa_caja_ls ($28/caja por defecto)
      - Domingo escalonado:
          * hasta domingo_umbral_cajas (10) -> domingo_tarifa_base ($28/caja)
          * excedente sobre umbral          -> domingo_tarifa_excedente ($40/caja)
      - Minimo semanal garantizado: si dias_trabajados >= dias_minimos_para_garantia
        y subtotal_destajo < minimo_semanal_garantizado ($2,350), se agrega complemento.
      - Merma > alerta_merma_pct (7%): dispara bandera de alerta SIN auto-descontar.
    """
    pago_ls = _r2(cajas_ls * tarifa_caja_ls)

    cajas_dom_base = min(cajas_domingo, domingo_umbral_cajas)
    cajas_dom_exc = max(Decimal("0.00"), cajas_domingo - domingo_umbral_cajas)

    pago_dom_base = _r2(cajas_dom_base * domingo_tarifa_base)
    pago_dom_exc = _r2(cajas_dom_exc * domingo_tarifa_excedente)

    subtotal_destajo = _r2(pago_ls + pago_dom_base + pago_dom_exc)

    if dias_trabajados >= dias_minimos_para_garantia and subtotal_destajo < minimo_semanal_garantizado:
        ajuste_minimo = _r2(minimo_semanal_garantizado - subtotal_destajo)
    else:
        ajuste_minimo = Decimal("0.00")

    total_pagar = _r2(subtotal_destajo + ajuste_minimo)

    total_cajas_brutas = cajas_ls + cajas_domingo + cajas_merma
    if total_cajas_brutas > 0:
        pct_merma = _r2((cajas_merma / total_cajas_brutas) * Decimal("100"))
    else:
        pct_merma = Decimal("0.00")

    return {
        "pago_ls": pago_ls,
        "pago_domingo_base": pago_dom_base,
        "pago_domingo_excedente": pago_dom_exc,
        "subtotal_destajo": subtotal_destajo,
        "ajuste_minimo_semanal": ajuste_minimo,
        "total_pagar": total_pagar,
        "porcentaje_merma_semanal": pct_merma,
        "alerta_merma": pct_merma > alerta_merma_pct,
    }
