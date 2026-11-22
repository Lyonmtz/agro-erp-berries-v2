import React, { useEffect, useState } from "react";
import { BarChart3, CheckCircle2, FileCheck2, RefreshCw, ShieldAlert, ShieldCheck } from "lucide-react";
import { ApiError, apiRequest } from "../api/client";
import type { AuthSession, CachedCatalogs } from "../types";

interface ExecutiveFinanceViewProps {
  session: AuthSession;
  catalogs: CachedCatalogs | null;
}

export const ExecutiveFinanceView: React.FC<ExecutiveFinanceViewProps> = ({
  session,
  catalogs,
}) => {
  const [empresaId, setEmpresaId] = useState<number>(catalogs?.empresas[0]?.id ?? 1);
  const [fechaInicio, setFechaInicio] = useState("2026-11-16");
  const [fechaFin, setFechaFin] = useState("2026-11-22");
  const [periodoClave, setPeriodoClave] = useState("2026-S47");

  const [reporte, setReporte] = useState<Record<string, unknown> | null>(null);
  const [integridad, setIntegridad] = useState<Record<string, unknown> | null>(null);
  const [auditoria, setAuditoria] = useState<Record<string, unknown> | null>(null);
  const [conciliacion, setConciliacion] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const loadAll = async () => {
    setError(null);
    setLoading(true);
    try {
      const [rep, integ, aud] = await Promise.all([
        apiRequest<Record<string, unknown>>(
          `/api/v1/finanzas/reportes/ejecutivo?empresa_id=${empresaId}&fecha_inicio=${fechaInicio}&fecha_fin=${fechaFin}&periodo_clave=${encodeURIComponent(
            periodoClave
          )}`,
          { token: session.access_token }
        ),
        apiRequest<Record<string, unknown>>(
          `/api/v1/finanzas/auditoria/integridad?empresa_id=${empresaId}`,
          { token: session.access_token }
        ).catch(() => null),
        apiRequest<Record<string, unknown>>(
          `/api/v1/finanzas/auditoria/eventos?empresa_id=${empresaId}&limit=15`,
          { token: session.access_token }
        ).catch(() => null),
      ]);
      setReporte(rep);
      setIntegridad(integ);
      setAuditoria(aud);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "No se pudo cargar el tablero financiero/auditoría."
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadAll();
  }, [empresaId]);

  const handleGenerarConciliacion = async () => {
    setError(null);
    try {
      const res = await apiRequest<Record<string, unknown>>("/api/v1/finanzas/conciliaciones", {
        method: "POST",
        token: session.access_token,
        body: { empresa_id: empresaId, fecha_inicio: fechaInicio, fecha_fin: fechaFin },
      });
      setConciliacion(res);
      await loadAll();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Error generando conciliación.");
    }
  };

  const kpisOp = (reporte?.kpis_operativos as Record<string, number> | undefined) ?? null;
  const kpisFin =
    (reporte?.kpis_financieros_separados as Record<string, number> | undefined) ?? null;

  return (
    <div className="space-y-5">
      {/* Filtros ejecutivos */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm flex flex-wrap gap-3 items-end justify-between">
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Empresa</label>
            <select
              value={empresaId}
              onChange={(e) => setEmpresaId(Number(e.target.value))}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
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
            <label className="block text-xs font-semibold text-slate-600 mb-1">Inicio</label>
            <input
              type="date"
              value={fechaInicio}
              onChange={(e) => setFechaInicio(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Fin</label>
            <input
              type="date"
              value={fechaFin}
              onChange={(e) => setFechaFin(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Periodo Presup.</label>
            <input
              type="text"
              value={periodoClave}
              onChange={(e) => setPeriodoClave(e.target.value)}
              className="w-28 rounded-lg border border-slate-300 px-3 py-2 text-sm font-mono"
            />
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={loadAll}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg border border-slate-300 hover:bg-slate-50 text-xs font-bold"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            Actualizar KPIs
          </button>
          <button
            onClick={handleGenerarConciliacion}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-emerald-800 hover:bg-emerald-700 text-white text-xs font-bold"
          >
            <FileCheck2 className="w-3.5 h-3.5" />
            Generar Snapshot Conciliación SHA-256
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl bg-rose-50 border border-rose-200 text-rose-900 px-4 py-3 text-xs font-semibold">
          {error}
        </div>
      )}

      {/* Tarjetas KPI separadas IMSS vs Especial */}
      {kpisOp && kpisFin && (
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
            <div className="text-[11px] font-bold uppercase text-slate-500">
              Cajas Exportación / Brecha Empaque
            </div>
            <div className="text-2xl font-extrabold text-emerald-900 mt-1">
              {kpisOp.cajas_exportacion}
            </div>
            <div className="text-xs text-slate-600 mt-1">
              Trasladadas: <strong>{kpisOp.cajas_trasladadas_empaque}</strong> · Delta:{" "}
              <strong
                className={
                  kpisOp.delta_cajas_campo_vs_empaque !== 0 ? "text-rose-700" : "text-emerald-700"
                }
              >
                {kpisOp.delta_cajas_campo_vs_empaque}
              </strong>
            </div>
          </div>

          <div className="bg-white rounded-xl border border-emerald-200 p-4 shadow-sm">
            <div className="text-[11px] font-bold uppercase text-emerald-700">
              Mano de Obra IMSS_MERQRY
            </div>
            <div className="text-2xl font-extrabold text-emerald-950 mt-1">
              ${kpisFin.mano_obra_imss_merqry.toLocaleString("es-MX", { minimumFractionDigits: 2 })}
            </div>
            <div className="text-[11px] text-emerald-700 mt-1">
              Circuito fiscal aislado (Merqry)
            </div>
          </div>

          <div className="bg-white rounded-xl border border-amber-200 p-4 shadow-sm">
            <div className="text-[11px] font-bold uppercase text-amber-800">
              Mano de Obra ESPECIAL_CONTABILIDAD
            </div>
            <div className="text-2xl font-extrabold text-amber-950 mt-1">
              $
              {kpisFin.mano_obra_especial_contabilidad.toLocaleString("es-MX", {
                minimumFractionDigits: 2,
              })}
            </div>
            <div className="text-[11px] text-amber-800 mt-1">
              Circuito separado Contabilidad (nunca Merqry)
            </div>
          </div>

          <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
            <div className="text-[11px] font-bold uppercase text-slate-500">
              Costo Directo Total / MO x Caja
            </div>
            <div className="text-2xl font-extrabold text-slate-900 mt-1">
              ${kpisFin.costo_total_directo.toLocaleString("es-MX", { minimumFractionDigits: 2 })}
            </div>
            <div className="text-xs text-slate-600 mt-1">
              MO/caja exp: <strong>${kpisFin.costo_mo_por_caja_exportable.toFixed(2)}</strong> · PHI
              bloqueados: <strong>{kpisOp.lotes_bloqueados_phi}</strong>
            </div>
          </div>
        </div>
      )}

      {/* Integridad Criptográfica SHA-256 + Última Conciliación */}
      <div className="grid md:grid-cols-2 gap-4">
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-2">
          <div className="flex items-center gap-2 font-bold text-slate-900">
            {integridad?.estado_global === "TAMPER_DETECTED" ? (
              <ShieldAlert className="w-5 h-5 text-rose-600" />
            ) : (
              <ShieldCheck className="w-5 h-5 text-emerald-700" />
            )}
            Verificador de Integridad SHA-256
          </div>
          {integridad ? (
            <div className="text-xs space-y-1">
              <div>
                Estado global:{" "}
                <strong
                  className={
                    integridad.estado_global === "INTEGRIDAD_OK"
                      ? "text-emerald-700"
                      : "text-rose-700"
                  }
                >
                  {String(integridad.estado_global)}
                </strong>
              </div>
              <div>
                Conciliaciones auditadas: <strong>{String(integridad.conciliaciones_verificadas)}</strong>{" "}
                · Alteraciones detectadas:{" "}
                <strong>{String(integridad.alteraciones_detectadas)}</strong>
              </div>
            </div>
          ) : (
            <p className="text-xs text-slate-500">Requiere permiso auditoria.leer (L3/L4).</p>
          )}
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm space-y-2">
          <div className="flex items-center gap-2 font-bold text-slate-900">
            <BarChart3 className="w-5 h-5 text-emerald-700" />
            Resumen de Seguridad &amp; Auditoría Universal
          </div>
          {auditoria ? (
            <div className="text-xs space-y-1">
              <div>
                Eventos recientes consultados: <strong>{String(auditoria.total_eventos)}</strong>
              </div>
              <div>
                Bloqueos firewall Merqry:{" "}
                <strong>
                  {String(
                    (auditoria.resumen_seguridad as Record<string, unknown> | undefined)
                      ?.bloqueos_firewall_merqry ?? 0
                  )}
                </strong>{" "}
                · Excepciones UPDATE_READY vencidas:{" "}
                <strong>
                  {String(
                    (auditoria.resumen_seguridad as Record<string, unknown> | undefined)
                      ?.excepciones_update_ready_vencidas ?? 0
                  )}
                </strong>
              </div>
            </div>
          ) : (
            <p className="text-xs text-slate-500">Requiere permiso auditoria.leer (L3/L4).</p>
          )}
        </div>
      </div>

      {conciliacion && (
        <div className="bg-emerald-50 border border-emerald-300 rounded-xl p-4 text-xs space-y-1">
          <div className="font-bold text-emerald-950 flex items-center gap-1.5">
            <CheckCircle2 className="w-4 h-4" />
            Conciliación generada ({String(conciliacion.estatus)}) — Hash SHA-256:
          </div>
          <code className="block font-mono text-[11px] break-all text-emerald-900">
            {String(conciliacion.hash_conciliacion_sha256)}
          </code>
        </div>
      )}
    </div>
  );
};
