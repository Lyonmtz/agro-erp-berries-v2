from decimal import Decimal
from typing import Dict

class MotorPagosCampo:
    @staticmethod
    def calcular_pago_diario(regla: Dict, cajas_exportacion: Decimal, cajas_nacional: Decimal, cajas_rezaga: Decimal, unidades_labor_cultural: Decimal = Decimal("0")) -> Dict[str, Decimal]:
        total_cajas = cajas_exportacion + cajas_nacional + cajas_rezaga
        porcentaje_rezaga = (cajas_rezaga * Decimal("100") / total_cajas) if total_cajas > 0 else Decimal("0")
        modalidad = regla["modalidad_pago"]
        jornal_base = Decimal(str(regla["tarifa_jornal_base"]))
        tarifa_unidad = Decimal(str(regla["tarifa_por_unidad"]))
        meta_minima = Decimal(str(regla["meta_minima_unidades"]))
        tarifa_excedente = Decimal(str(regla["tarifa_excedente_unidad"]))
        max_rezaga = Decimal(str(regla["porcentaje_rezaga_maximo"]))
        bono_unidad = Decimal(str(regla["bono_calidad_por_unidad"]))
        pago_jornal = Decimal("0.00")
        pago_destajo = Decimal("0.00")
        pago_bono = Decimal("0.00")
        unidades_totales = total_cajas if total_cajas > 0 else unidades_labor_cultural
        if modalidad == "JORNAL_PURO":
            pago_jornal = jornal_base
        elif modalidad == "DESTAJO_PURO":
            pago_destajo = unidades_totales * tarifa_unidad
        elif modalidad == "MIXTO_GARANTIA":
            pago_jornal = jornal_base
            if unidades_totales > meta_minima:
                pago_destajo = (unidades_totales - meta_minima) * tarifa_excedente
        if total_cajas > 0 and porcentaje_rezaga <= max_rezaga and bono_unidad > 0:
            pago_bono = cajas_exportacion * bono_unidad
        return {
            "total_cajas": round(total_cajas, 2),
            "porcentaje_rezaga": round(porcentaje_rezaga, 2),
            "pago_jornal_base": round(pago_jornal, 2),
            "pago_destajo": round(pago_destajo, 2),
            "pago_bono_calidad": round(pago_bono, 2),
            "total_percepcion_dia": round(pago_jornal + pago_destajo + pago_bono, 2)
        }
