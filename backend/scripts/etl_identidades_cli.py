"""CLI auditable para migracion de identidades desde CSV hacia PostgreSQL (Fase 1).

Uso:
    python -m scripts.etl_identidades_cli --csv /ruta/padron.csv --empresa NFA --fuente "Padron_2026"

Reglas estrictas:
- Concilia unicamente por CURP valido y exacto.
- NUNCA fusiona personas automaticamente por coincidencia de nombre o telefono;
  todo conflicto se envia a etl_cuarentena_identidad para revision humana.
"""

import argparse
import asyncio
import csv
import json
from pathlib import Path

from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.modules.identidad.etl_service import ejecutar_etl_identidades


async def _run(csv_path: Path, empresa_clave: str, fuente: str) -> None:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        registros = list(csv.DictReader(fh))

    async with AsyncSessionLocal() as session:
        emp_id = (
            await session.execute(
                text("SELECT id FROM empresas WHERE clave = :c"),
                {"c": empresa_clave.strip().upper()},
            )
        ).scalar()
        if emp_id is None:
            raise SystemExit(f"Empresa '{empresa_clave}' no encontrada en tabla empresas.")

        res = await ejecutar_etl_identidades(
            session,
            fuente_nombre=fuente,
            empresa_id=emp_id,
            registros=registros,
            actor=None,
        )
        await session.commit()
        print(json.dumps(res, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="ETL auditable de identidades (Fase 1)")
    parser.add_argument("--csv", required=True, type=Path, help="Ruta al archivo CSV de entrada")
    parser.add_argument("--empresa", required=True, help="Clave de empresa (NFA o BIO)")
    parser.add_argument("--fuente", required=True, help="Nombre auditable de la fuente")
    args = parser.parse_args()
    asyncio.run(_run(args.csv, args.empresa, args.fuente))


if __name__ == "__main__":
    main()
