import React, { useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardList,
  Clock,
  RefreshCw,
  Scissors,
  Search,
  Truck,
} from "lucide-react";
import type {
  AuthSession,
  CachedCatalogs,
  DailyEligibleWorker,
  EligibilitySnapshot,
  OutboxCommand,
} from "../types";
import { enqueueOfflineCommand, syncSingleCommand } from "../offline/syncEngine";

interface FieldTabletViewProps {
  session: AuthSession;
  snapshot: EligibilitySnapshot | null;
  catalogs: CachedCatalogs | null;
  simulatedOffline: boolean;
  onRefreshSnapshot: () => Promise<void>;
  onOutboxUpdated: () => Promise<void>;
}

type FieldTab = "cosecha" | "culturales" | "trasplante";

export const FieldTabletView: React.FC<FieldTabletViewProps> = ({
  session,
  snapshot,
  catalogs,
  simulatedOffline,
  onRefreshSnapshot,
  onOutboxUpdated,
}) => {
  const [subTab, setSubTab] = useState<FieldTab>("cosecha");
  const [workerSearch, setWorkerSearch] = useState("");
  const [selectedWorkerId, setSelectedWorkerId] = useState<string>("");
  const [syncingSnap, setSyncingSnap] = useState(false);
  const [feedback, setFeedback] = useState<{ kind: "ok" | "warn" | "err"; text: string } | null>(
    null
  );

  const todayIso = new Date().toISOString().slice(0, 10);

  // Estado formulario Cosecha
  const [loteId, setLoteId] = useState<number>(catalogs?.lotes[0]?.id ?? 1);
  const [cajasExp, setCajasExp] = useState<number>(10);
  const [cajasNac, setCajasNac] = useState<number>(1);
  const [cajasMerma, setCajasMerma] = useState<number>(0);
  const [codigoCaja, setCodigoCaja] = useState<string>(
    () => `CAJA-${todayIso.replace(/-/g, "")}-${Math.floor(1000 + Math.random() * 9000)}`
  );

  // Estado formulario Culturales
  const [laborCodigo, setLaborCodigo] = useState("PODA_BROTES");
  const [unidadMedida, setUnidadMedida] = useState("SURCO");
  const [metaDiaria, setMetaDiaria] = useState(12);
  const [cantidadRealizada, setCantidadRealizada] = useState(12);
  const [minutosTrabajados, setMinutosTrabajados] = useState(480);
  const [minutosPausa, setMinutosPausa] = useState(30);

  // Estado formulario Trasplante Multi-Camión
  const [codigoCamion, setCodigoCamion] = useState(
    () => `CAM-${todayIso.replace(/-/g, "")}-${Math.floor(10 + Math.random() * 89)}`
  );
  const [proveedor, setProveedor] = useState("Mastronardi Produce Limited");
  const [cajasPlasticas, setCajasPlasticas] = useState(26);
  const [selectedUnidadId, setSelectedUnidadId] = useState<number>(
    catalogs?.unidades[0]?.id ?? 3
  );

  const snapshotExpired = useMemo(() => {
    if (!snapshot) return true;
    return Date.now() > new Date(snapshot.expires_at).getTime();
  }, [snapshot]);

  const filteredWorkers = useMemo(() => {
    const list = snapshot?.workers ?? [];
    const q = workerSearch.trim().toLowerCase();
    if (!q) return list;
    return list.filter(
      (w) =>
        w.nombre_operativo.toLowerCase().includes(q) ||
        w.numero_empleado.toLowerCase().includes(q) ||
        w.clave_interna_qr.toLowerCase().includes(q)
    );
  }, [snapshot, workerSearch]);

  const activeWorker: DailyEligibleWorker | undefined = useMemo(() => {
    const list = snapshot?.workers ?? [];
    return list.find((w) => w.person_id === selectedWorkerId) ?? list[0];
  }, [snapshot, selectedWorkerId]);

  const activeLote = useMemo(() => {
    return catalogs?.lotes.find((l) => l.id === loteId) ?? catalogs?.lotes[0];
  }, [catalogs, loteId]);

  const totalCajas = cajasExp + cajasNac + cajasMerma;
  const pctMerma = totalCajas > 0 ? (cajasMerma / totalCajas) * 100 : 0;

  const dispatchViaOutbox = async (
    kind: OutboxCommand["command_kind"],
    endpoint: string,
    label: string,
    payload: Record<string, unknown>
  ) => {
    const queued = await enqueueOfflineCommand({
      command_kind: kind,
      endpoint,
      label,
      payload,
    });
    const finalCmd = await syncSingleCommand(queued, session.access_token, simulatedOffline);
    await onOutboxUpdated();

    if (finalCmd.status === "COMMITTED") {
      setFeedback({
        kind: "ok",
        text: `Confirmado en servidor (${finalCmd.client_command_id.slice(0, 8)}…) — ${label}`,
      });
    } else if (finalCmd.status === "QUEUED" || finalCmd.status === "RETRY_WAIT") {
      setFeedback({
        kind: "warn",
        text: `Guardado en IndexedDB Offline (${finalCmd.client_command_id.slice(0, 8)}…). Se sincronizará automáticamente al recuperar señal.`,
      });
    } else {
      setFeedback({
        kind: "err",
        text: `Rechazado (${finalCmd.status}): ${finalCmd.last_error}`,
      });
    }
  };

  const handleCaptureCosecha = async (e: React.FormEvent) => {
    e.preventDefault();
    setFeedback(null);
    if (snapshotExpired) {
      setFeedback({
        kind: "err",
        text: "Snapshot DailyEligibleWorker vencido (TTL 12h). Sincronice antes de capturar.",
      });
      return;
    }
    if (!activeWorker || !activeLote) {
      setFeedback({ kind: "err", text: "Seleccione un trabajador elegible y un lote válido." });
      return;
    }
    await dispatchViaOutbox(
      "COSECHA_CAPTURA",
      "/api/v1/cosecha/capturas",
      `Cosecha ${activeWorker.numero_empleado} · ${cajasExp}E/${cajasNac}N/${cajasMerma}M (${activeLote.codigo_lote})`,
      {
        fecha: todayIso,
        lote_id: activeLote.id,
        persona_id: activeWorker.person_id,
        relacion_laboral_id: activeWorker.relacion_laboral_id,
        modo_captura: "VIVO",
        codigo_trazabilidad_caja: codigoCaja.trim(),
        cajas_exportacion: cajasExp,
        cajas_nacional: cajasNac,
        cajas_merma_rezaga: cajasMerma,
        nip_confirmado: true,
      }
    );
    setCodigoCaja(`CAJA-${todayIso.replace(/-/g, "")}-${Math.floor(1000 + Math.random() * 9000)}`);
  };

  const handleCaptureCultural = async (e: React.FormEvent) => {
    e.preventDefault();
    setFeedback(null);
    if (snapshotExpired || !activeWorker || !activeLote) {
      setFeedback({
        kind: "err",
        text: "Requiere snapshot vigente, trabajador elegible y lote válido.",
      });
      return;
    }
    await dispatchViaOutbox(
      "CULTURAL_DIARIO",
      "/api/v1/cosecha/culturales",
      `Cultural ${laborCodigo} · ${activeWorker.numero_empleado} (${cantidadRealizada} ${unidadMedida})`,
      {
        fecha: todayIso,
        lote_id: activeLote.id,
        persona_id: activeWorker.person_id,
        relacion_laboral_id: activeWorker.relacion_laboral_id,
        labor_codigo: laborCodigo.trim().toUpperCase(),
        unidad_medida: unidadMedida,
        meta_diaria: metaDiaria,
        cantidad_realizada: cantidadRealizada,
        minutos_trabajados: minutosTrabajados,
        minutos_pausa: minutosPausa,
      }
    );
  };

  const handleDeclareTruck = async (e: React.FormEvent) => {
    e.preventDefault();
    setFeedback(null);
    const unidad =
      catalogs?.unidades.find((u) => u.id === selectedUnidadId) ?? catalogs?.unidades[0];
    if (!unidad) {
      setFeedback({ kind: "err", text: "Sincronice catálogos para cargar unidades operativas." });
      return;
    }
    await dispatchViaOutbox(
      "TRASPLANTE_CAMION",
      "/api/v1/trasplante/camiones/declare",
      `Camión ${codigoCamion} · ${cajasPlasticas} cajas (${unidad.clave})`,
      {
        empresa_id: unidad.empresa_id,
        sucursal_id: unidad.sucursal_id,
        unidad_operativa_id: unidad.id,
        codigo_camion: codigoCamion.trim().toUpperCase(),
        proveedor: proveedor.trim(),
        cajas_plasticas_recibidas: cajasPlasticas,
      }
    );
    setCodigoCamion(`CAM-${todayIso.replace(/-/g, "")}-${Math.floor(10 + Math.random() * 89)}`);
  };

  const handleCierreTecnicoUnidad = async () => {
    setFeedback(null);
    const unidad =
      catalogs?.unidades.find((u) => u.id === selectedUnidadId) ?? catalogs?.unidades[0];
    if (!unidad) return;
    await dispatchViaOutbox(
      "CIERRE_OPERATIVO",
      "/api/v1/cosecha/cierres",
      `Cierre Técnico UNIDAD ${unidad.clave} (${todayIso})`,
      {
        empresa_id: unidad.empresa_id,
        sucursal_id: unidad.sucursal_id,
        unidad_operativa_id: unidad.id,
        fecha: todayIso,
        alcance_cierre: "UNIDAD",
      }
    );
  };

  const refreshSnap = async () => {
    setSyncingSnap(true);
    try {
      await onRefreshSnapshot();
    } finally {
      setSyncingSnap(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Banner contrato DailyEligibleWorker.v0.1 con TTL */}
      <div
        className={`rounded-xl border p-4 flex flex-wrap items-center justify-between gap-3 ${
          snapshotExpired
            ? "bg-rose-50 border-rose-300 text-rose-900"
            : "bg-emerald-50 border-emerald-200 text-emerald-950"
        }`}
      >
        <div className="flex items-start gap-3">
          <Clock className="w-5 h-5 mt-0.5 shrink-0" />
          <div className="text-xs space-y-0.5">
            <div className="font-bold text-sm">
              Snapshot Elegibilidad ({snapshot?.contract_version ?? "Sin descargar"}) —{" "}
              {snapshot?.workers.length ?? 0} trabajadores elegibles
            </div>
            <div>
              {snapshot ? (
                <>
                  Fecha operativa: <strong>{snapshot.fecha}</strong> · Vence:{" "}
                  <strong>{new Date(snapshot.expires_at).toLocaleString("es-MX")}</strong>{" "}
                  {snapshotExpired && <span className="font-bold text-rose-700">(VENCIDO)</span>}
                </>
              ) : (
                "Descargue el snapshot diario antes de salir a campo sin señal."
              )}
            </div>
          </div>
        </div>
        <button
          onClick={refreshSnap}
          disabled={syncingSnap || simulatedOffline}
          className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-emerald-800 hover:bg-emerald-700 disabled:opacity-50 text-white text-xs font-bold shadow-sm"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${syncingSnap ? "animate-spin" : ""}`} />
          Actualizar Snapshot &amp; Catálogos
        </button>
      </div>

      {/* Selector sub-módulo Tablet */}
      <div className="grid grid-cols-3 gap-2 bg-slate-200/70 p-1.5 rounded-xl">
        <button
          onClick={() => setSubTab("cosecha")}
          className={`flex items-center justify-center gap-2 py-2.5 rounded-lg text-xs sm:text-sm font-bold transition ${
            subTab === "cosecha"
              ? "bg-white text-emerald-900 shadow"
              : "text-slate-600 hover:text-slate-900"
          }`}
        >
          <ClipboardList className="w-4 h-4" />
          Cosecha
        </button>
        <button
          onClick={() => setSubTab("culturales")}
          className={`flex items-center justify-center gap-2 py-2.5 rounded-lg text-xs sm:text-sm font-bold transition ${
            subTab === "culturales"
              ? "bg-white text-emerald-900 shadow"
              : "text-slate-600 hover:text-slate-900"
          }`}
        >
          <Scissors className="w-4 h-4" />
          Culturales
        </button>
        <button
          onClick={() => setSubTab("trasplante")}
          className={`flex items-center justify-center gap-2 py-2.5 rounded-lg text-xs sm:text-sm font-bold transition ${
            subTab === "trasplante"
              ? "bg-white text-emerald-900 shadow"
              : "text-slate-600 hover:text-slate-900"
          }`}
        >
          <Truck className="w-4 h-4" />
          Trasplante
        </button>
      </div>

      {feedback && (
        <div
          className={`rounded-xl px-4 py-3 text-xs font-semibold flex items-center gap-2 border ${
            feedback.kind === "ok"
              ? "bg-emerald-50 border-emerald-300 text-emerald-900"
              : feedback.kind === "warn"
              ? "bg-amber-50 border-amber-300 text-amber-900"
              : "bg-rose-50 border-rose-300 text-rose-900"
          }`}
        >
          {feedback.kind === "ok" ? (
            <CheckCircle2 className="w-4 h-4 shrink-0" />
          ) : (
            <AlertTriangle className="w-4 h-4 shrink-0" />
          )}
          <span>{feedback.text}</span>
        </div>
      )}

      {/* Selector de trabajador + lote compartido para Cosecha y Culturales */}
      {subTab !== "trasplante" && (
        <div className="bg-white rounded-xl border border-slate-200 p-4 grid md:grid-cols-2 gap-4 shadow-sm">
          <div className="space-y-2">
            <label className="text-xs font-bold uppercase text-slate-600 flex items-center gap-1.5">
              <Search className="w-3.5 h-3.5" />
              Trabajador (QR / No. Empleado / Nombre)
            </label>
            <input
              type="text"
              value={workerSearch}
              onChange={(e) => setWorkerSearch(e.target.value)}
              placeholder="Escanear QR o buscar EMP-2001..."
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
            <select
              value={activeWorker?.person_id ?? ""}
              onChange={(e) => setSelectedWorkerId(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm font-medium bg-slate-50"
            >
              {filteredWorkers.map((w) => (
                <option key={w.person_id} value={w.person_id}>
                  {w.numero_empleado} — {w.nombre_operativo} ({w.funcion_operativa_vigente})
                </option>
              ))}
            </select>
            {activeWorker && (
              <div className="flex flex-wrap gap-1">
                {activeWorker.operaciones_autorizadas.map((op) => (
                  <span
                    key={op}
                    className="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-900 text-[10px] font-bold"
                  >
                    {op}
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="space-y-2">
            <label className="text-xs font-bold uppercase text-slate-600 block">
              Lote de Producción
            </label>
            <select
              value={activeLote?.id ?? ""}
              onChange={(e) => setLoteId(Number(e.target.value))}
              className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm font-medium bg-slate-50"
            >
              {(catalogs?.lotes ?? []).map((l) => (
                <option key={l.id} value={l.id}>
                  {l.codigo_lote} · {l.cultivo} ({l.variedad}) — {l.estatus_fitosanitario}
                </option>
              ))}
            </select>
            {activeLote && activeLote.estatus_fitosanitario !== "LIBRE_CORTE" && (
              <div className="p-2.5 rounded-lg bg-rose-100 border border-rose-300 text-rose-900 text-xs font-bold flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                BLOQUEO FITOSANITARIO (PHI): {activeLote.estatus_fitosanitario}
              </div>
            )}
          </div>
        </div>
      )}

      {/* SUB-TAB COSECHA */}
      {subTab === "cosecha" && (
        <form
          onSubmit={handleCaptureCosecha}
          className="bg-white rounded-xl border border-slate-200 p-5 space-y-4 shadow-sm"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-bold text-base text-slate-900">
              Captura Offline-First de Cosecha ({todayIso})
            </h2>
            <button
              type="button"
              onClick={handleCierreTecnicoUnidad}
              className="text-xs px-3 py-1.5 rounded-lg border border-amber-400 bg-amber-50 hover:bg-amber-100 text-amber-900 font-bold"
            >
              Ejecutar Cierre Técnico Unidad
            </button>
          </div>

          <div className="grid sm:grid-cols-4 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">
                Folio Trazabilidad Caja
              </label>
              <input
                type="text"
                value={codigoCaja}
                onChange={(e) => setCodigoCaja(e.target.value)}
                required
                className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm font-mono"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-emerald-700 mb-1">
                Cajas Exportación
              </label>
              <input
                type="number"
                min={0}
                step="0.5"
                value={cajasExp}
                onChange={(e) => setCajasExp(Number(e.target.value))}
                className="w-full rounded-lg border border-emerald-300 px-3 py-2.5 text-lg font-bold text-center text-emerald-900"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-blue-700 mb-1">
                Cajas Nacional
              </label>
              <input
                type="number"
                min={0}
                step="0.5"
                value={cajasNac}
                onChange={(e) => setCajasNac(Number(e.target.value))}
                className="w-full rounded-lg border border-blue-300 px-3 py-2.5 text-lg font-bold text-center text-blue-900"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-rose-700 mb-1">
                Merma / Rezaga
              </label>
              <input
                type="number"
                min={0}
                step="0.5"
                value={cajasMerma}
                onChange={(e) => setCajasMerma(Number(e.target.value))}
                className="w-full rounded-lg border border-rose-300 px-3 py-2.5 text-lg font-bold text-center text-rose-900"
              />
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 bg-slate-50 rounded-lg px-3.5 py-2.5 text-xs">
            <span>
              Total cajas: <strong>{totalCajas}</strong> · Merma:{" "}
              <strong className={pctMerma > 7 ? "text-rose-700" : "text-emerald-700"}>
                {pctMerma.toFixed(1)}%
              </strong>
            </span>
            {pctMerma > 7 && (
              <span className="px-2 py-0.5 rounded bg-rose-100 text-rose-800 font-bold">
                ALERTA MERMA &gt; 7%
              </span>
            )}
          </div>

          <button
            type="submit"
            className="w-full bg-emerald-800 hover:bg-emerald-700 text-white py-3.5 rounded-xl font-bold text-sm shadow transition"
          >
            Guardar Captura de Cosecha (Idempotente / Offline-First)
          </button>
        </form>
      )}

      {/* SUB-TAB CULTURALES */}
      {subTab === "culturales" && (
        <form
          onSubmit={handleCaptureCultural}
          className="bg-white rounded-xl border border-slate-200 p-5 space-y-4 shadow-sm"
        >
          <h2 className="font-bold text-base text-slate-900">
            Labores Culturales Individuales ({todayIso})
          </h2>
          <div className="grid sm:grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">
                Código de Labor
              </label>
              <input
                type="text"
                value={laborCodigo}
                onChange={(e) => setLaborCodigo(e.target.value)}
                required
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm uppercase"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">
                Unidad de Medida
              </label>
              <select
                value={unidadMedida}
                onChange={(e) => setUnidadMedida(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              >
                {["SURCO", "METRO_LINEAL", "PLANTA", "MACETA", "HORA", "JORNAL", "CAJA"].map(
                  (u) => (
                    <option key={u} value={u}>
                      {u}
                    </option>
                  )
                )}
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">
                Meta Diaria
              </label>
              <input
                type="number"
                min={0}
                value={metaDiaria}
                onChange={(e) => setMetaDiaria(Number(e.target.value))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">
                Cantidad Realizada
              </label>
              <input
                type="number"
                min={0.1}
                step="0.5"
                value={cantidadRealizada}
                onChange={(e) => setCantidadRealizada(Number(e.target.value))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm font-bold"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">
                Minutos Trabajados
              </label>
              <input
                type="number"
                min={1}
                value={minutosTrabajados}
                onChange={(e) => setMinutosTrabajados(Number(e.target.value))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">
                Minutos Pausa
              </label>
              <input
                type="number"
                min={0}
                value={minutosPausa}
                onChange={(e) => setMinutosPausa(Number(e.target.value))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </div>
          </div>

          <button
            type="submit"
            className="w-full bg-emerald-800 hover:bg-emerald-700 text-white py-3.5 rounded-xl font-bold text-sm shadow transition"
          >
            Registrar Labor Cultural Individual (Offline-First)
          </button>
        </form>
      )}

      {/* SUB-TAB TRASPLANTE MULTI-CAMIÓN */}
      {subTab === "trasplante" && (
        <form
          onSubmit={handleDeclareTruck}
          className="bg-white rounded-xl border border-slate-200 p-5 space-y-4 shadow-sm"
        >
          <h2 className="font-bold text-base text-slate-900">
            Declarar Camión de Trasplante (Idempotente · Fase 3A)
          </h2>
          <div className="grid sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">
                Unidad Operativa Autorizada
              </label>
              <select
                value={selectedUnidadId}
                onChange={(e) => setSelectedUnidadId(Number(e.target.value))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm"
              >
                {(catalogs?.unidades ?? []).map((u) => (
                  <option key={u.id} value={u.id}>
                    #{u.id} · {u.clave} — {u.nombre} (Emp {u.empresa_id})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">
                Código Camión
              </label>
              <input
                type="text"
                value={codigoCamion}
                onChange={(e) => setCodigoCamion(e.target.value)}
                required
                className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm font-mono uppercase"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">
                Proveedor de Planta
              </label>
              <input
                type="text"
                value={proveedor}
                onChange={(e) => setProveedor(e.target.value)}
                required
                className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">
                Cajas Plásticas Recibidas
              </label>
              <input
                type="number"
                min={1}
                value={cajasPlasticas}
                onChange={(e) => setCajasPlasticas(Number(e.target.value))}
                required
                className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm font-bold"
              />
            </div>
          </div>

          <button
            type="submit"
            className="w-full bg-emerald-800 hover:bg-emerald-700 text-white py-3.5 rounded-xl font-bold text-sm shadow transition"
          >
            Declarar Camión con client_command_id (Offline-First)
          </button>
        </form>
      )}
    </div>
  );
};
