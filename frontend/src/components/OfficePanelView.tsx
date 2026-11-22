import React, { useEffect, useState } from "react";
import { Award, Calculator, Lock, RefreshCw, ShieldAlert, ShieldCheck } from "lucide-react";
import { ApiError, apiRequest } from "../api/client";
import type { AuthSession, CachedCatalogs, MerqryWriterStatus } from "../types";

interface OfficePanelViewProps {
  session: AuthSession;
  catalogs: CachedCatalogs | null;
}

export const OfficePanelView: React.FC<OfficePanelViewProps> = ({ session, catalogs }) => {
  const [writerStatus, setWriterStatus] = useState<MerqryWriterStatus | null>(null);
  const [merqryReadStatus, setMerqryReadStatus] = useState<Record<string, unknown> | null>(null);
  const [outboxCount, setOutboxCount] = useState<number>(0);
  const [honorRows, setHonorRows] = useState<Array<Record<string, unknown>>>([]);
  const [statusError, setStatusError] = useState<string | null>(null);

  // Generador de prenómina semanal
  const [empresaId, setEmpresaId] = useState<number>(catalogs?.empresas[0]?.id ?? 1);
  const [anio, setAnio] = useState<number>(2026);
  const [semana, setSemana] = useState<number>(47);
  const [fechaInicio, setFechaInicio] = useState<string>("2026-11-16");
  const [fechaFin, setFechaFin] = useState<string>("2026-11-22");
  const [prenominaResult, setPrenominaResult] = useState<Record<string, unknown> | null>(null);
  const [prenominaError, setPrenominaError] = useState<string | null>(null);

  const loadOfficeData = async () => {
    setStatusError(null);
    try {
      const [mw, mr, ob] = await Promise.all([
        apiRequest<MerqryWriterStatus>("/api/v1/merqry-writer/status", {
          token: session.access_token,
        }),
        apiRequest<Record<string, unknown>>("/api/v1/merqry/status", {
          token: session.access_token,
        }),
        apiRequest<{ count: number }>("/api/v1/merqry-writer/outbox?limit=20", {
          token: session.access_token,
        }),
      ]);
      setWriterStatus(mw);
      setMerqryReadStatus(mr);
      setOutboxCount(ob.count);
    } catch (err) {
      setStatusError(
        err instanceof ApiError
          ? `Acceso restringido / error: ${err.message}`
          : "Error consultando estado de oficina."
      );
    }

    try {
      const honor = await apiRequest<{ ranking?: Array<Record<string, unknown>> }>(
        `/api/v1/cosecha/cuadro-honor?empresa_id=${empresaId}`,
        { token: session.access_token }
      );
      setHonorRows(honor.ranking ?? []);
    } catch {
      setHonorRows([]);
    }
  };

  useEffect(() => {
    void loadOfficeData();
  }, [empresaId]);

  const handleGenerarPrenomina = async (e: React.FormEvent) => {
    e.preventDefault();
    setPrenominaError(null);
    setPrenominaResult(null);
    try {
      const res = await apiRequest<Record<string, unknown>>("/api/v1/prenomina/semanal/generar", {
        method: "POST",
        token: session.access_token,
        body: {
          empresa_id: empresaId,
          anio,
          semana_seah: semana,
          fecha_inicio: fechaInicio,
          fecha_fin: fechaFin,
        },
      });
      setPrenominaResult(res);
    } catch (err) {
      setPrenominaError(err instanceof ApiError ? err.message : "Error generando prenómina semanal.");
    }
  };

  return (
    <div className="space-y-5">
      {/* 1. Panel Seguridad Merqry Read-Only & merqry_writer (Fail-Closed) */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-emerald-700" />
            <h2 className="font-bold text-slate-900">
              Seguridad Merqry: Solo Lectura &amp; Escritura Controlada (Fail-Closed)
            </h2>
          </div>
          <button
            onClick={loadOfficeData}
            className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-slate-300 hover:bg-slate-50 font-semibold"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Refrescar
          </button>
        </div>

        {statusError && (
          <div className="rounded-lg bg-amber-50 border border-amber-200 text-amber-900 px-3.5 py-2.5 text-xs font-medium">
            {statusError}
          </div>
        )}

        {writerStatus && (
          <div className="grid md:grid-cols-3 gap-3 text-xs">
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3.5 space-y-1">
              <div className="font-bold text-emerald-900 flex items-center gap-1.5">
                <Lock className="w-3.5 h-3.5" />
                merqry_writer
              </div>
              <div>
                Estado:{" "}
                <strong className="text-emerald-800">
                  {writerStatus.merqry_write_enabled ? "ACTIVO" : "APAGADO POR DEFECTO"}
                </strong>
              </div>
              <div>
                Modo: <strong>{writerStatus.merqry_write_mode}</strong> · Outbox PG:{" "}
                <strong>{outboxCount}</strong>
              </div>
            </div>

            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3.5 space-y-1">
              <div className="font-bold text-slate-900">Firewall de Circuitos</div>
              <div>
                Único permitido:{" "}
                <span className="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-900 font-bold">
                  {writerStatus.allowed_circuit}
                </span>
              </div>
              <div className="text-rose-700 font-semibold">
                Bloqueado: ESPECIAL_CONTABILIDAD · &apos;Nomina Especial&apos;
              </div>
            </div>

            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3.5 space-y-1">
              <div className="font-bold text-slate-900">Mapeo Empresas (Invertido)</div>
              <div>
                PG <strong>BIO</strong> → Merqry <strong>Emp 1 / Suc 1</strong>
              </div>
              <div>
                PG <strong>NFA</strong> → Merqry <strong>Emp 2 / Suc 2</strong>
              </div>
              <div className="text-[11px] text-slate-500">
                Respaldo congelado: {writerStatus.frozen_readonly_schemas.join(", ")}
              </div>
            </div>
          </div>
        )}

        {merqryReadStatus && (
          <div className="text-[11px] text-slate-600 flex flex-wrap gap-2 items-center">
            <ShieldAlert className="w-3.5 h-3.5 text-emerald-700" />
            <span>
              Espejo lectura: <strong>{String(merqryReadStatus.integration_mode)}</strong> ·
              Circuitos separados:{" "}
              <strong>
                {Array.isArray(merqryReadStatus.circuitos_separados)
                  ? merqryReadStatus.circuitos_separados.join(" | ")
                  : "IMSS_MERQRY vs ESPECIAL_CONTABILIDAD"}
              </strong>
            </span>
          </div>
        )}
      </div>

      {/* 2. Motor de Prenómina Semanal (L-S $28 + Domingo escalonado + Mínimo $2,350) */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-4">
        <div className="flex items-center gap-2">
          <Calculator className="w-5 h-5 text-emerald-700" />
          <h2 className="font-bold text-slate-900">
            Prenómina Semanal Configurable (Solo Capturas Autorizadas)
          </h2>
        </div>

        <form onSubmit={handleGenerarPrenomina} className="grid sm:grid-cols-5 gap-3 items-end">
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Empresa</label>
            <select
              value={empresaId}
              onChange={(e) => setEmpresaId(Number(e.target.value))}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              {(catalogs?.empresas ?? [{ id: 1, clave: "NFA", nombre_comercial: "NFA" }]).map(
                (emp) => (
                  <option key={emp.id} value={emp.id}>
                    {emp.clave} — {emp.nombre_comercial}
                  </option>
                )
              )}
            </select>
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Año</label>
            <input
              type="number"
              value={anio}
              onChange={(e) => setAnio(Number(e.target.value))}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Semana SEAH</label>
            <input
              type="number"
              min={1}
              max={53}
              value={semana}
              onChange={(e) => setSemana(Number(e.target.value))}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Fecha Inicio</label>
            <input
              type="date"
              value={fechaInicio}
              onChange={(e) => setFechaInicio(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Fecha Fin</label>
            <input
              type="date"
              value={fechaFin}
              onChange={(e) => setFechaFin(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
          <button
            type="submit"
            className="sm:col-span-5 bg-emerald-800 hover:bg-emerald-700 text-white py-2.5 rounded-xl font-bold text-sm"
          >
            Calcular Prenómina Semanal (Separada IMSS_MERQRY vs ESPECIAL_CONTABILIDAD)
          </button>
        </form>

        {prenominaError && (
          <div className="rounded-lg bg-rose-50 border border-rose-200 text-rose-900 px-3.5 py-2.5 text-xs font-semibold">
            {prenominaError}
          </div>
        )}

        {prenominaResult && (
          <pre className="bg-slate-900 text-emerald-200 p-4 rounded-xl text-xs overflow-x-auto">
            {JSON.stringify(prenominaResult, null, 2)}
          </pre>
        )}
      </div>

      {/* 3. Cuadro de Honor */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-3">
        <div className="flex items-center gap-2">
          <Award className="w-5 h-5 text-amber-600" />
          <h2 className="font-bold text-slate-900">Cuadro de Honor de Cosecha</h2>
        </div>
        {honorRows.length === 0 ? (
          <p className="text-xs text-slate-500">
            Sin capturas acumuladas para la empresa seleccionada en el periodo actual.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-100 text-slate-600 uppercase">
                <tr>
                  <th className="px-3 py-2">#</th>
                  <th className="px-3 py-2">Empleado</th>
                  <th className="px-3 py-2">Cajas Exportación</th>
                  <th className="px-3 py-2">Merma %</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {honorRows.map((row, idx) => (
                  <tr key={idx}>
                    <td className="px-3 py-2 font-bold">{idx + 1}</td>
                    <td className="px-3 py-2">{String(row.nombre_completo ?? row.numero_empleado ?? "-")}</td>
                    <td className="px-3 py-2 font-bold text-emerald-800">
                      {String(row.total_cajas_exportacion ?? 0)}
                    </td>
                    <td className="px-3 py-2">{String(row.porcentaje_merma_promedio ?? 0)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
