from typing import Dict, Any

class MotorPsicometrico:
    @staticmethod
    def evaluar_bateria(codigo_bateria: str, respuestas: Dict[str, Any]) -> Dict[str, Any]:
        if codigo_bateria == "ZAVIC_OP":
            puntajes = {"moralidad": 0, "legalidad": 0, "compromiso": 0, "apego_normas": 0}
            for _, val in respuestas.items():
                dim = val.get("dimension")
                pts = float(val.get("puntos", 0))
                if dim in puntajes:
                    puntajes[dim] += pts
            promedio = round(sum(puntajes.values()) / max(len(puntajes), 1), 2)
            dictamen = "APTO_OPERATIVO" if promedio >= 70 and puntajes["legalidad"] >= 65 else "REVISION_RH"
            return {"puntaje": promedio, "dimensiones": puntajes, "dictamen": dictamen}
        elif codigo_bateria == "CLEAVER_SUP":
            disc = {"D": 0, "I": 0, "S": 0, "C": 0}
            for _, val in respuestas.items():
                mas, menos = val.get("mas"), val.get("menos")
                if mas in disc: disc[mas] += 10
                if menos in disc: disc[menos] -= 5
            score = min(100.0, max(0.0, 50 + (disc["D"] + disc["C"]) * 0.8))
            dictamen = "LIDER_OPERATIVO_APTO" if score >= 70 else "BAJO_EMPUJE_CONTROL"
            return {"puntaje": round(score, 2), "perfil_disc": disc, "dictamen": dictamen}
        total_obtenido = sum(float(v.get("puntos", 0)) for v in respuestas.values())
        total_maximo = sum(float(v.get("max_puntos", 10)) for v in respuestas.values()) or 1
        porcentaje = round((total_obtenido / total_maximo) * 100, 2)
        return {"puntaje": porcentaje, "dictamen": "APROBADO" if porcentaje >= 75 else "NO_APROBADO"}
