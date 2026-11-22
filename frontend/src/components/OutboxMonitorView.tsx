import React, { useState } from "react";
import { CheckCircle2, CloudUpload, RefreshCw, Search, Trash2, AlertOctagon } from "lucide-react";
import type { AuthSession, OutboxCommand } from "../types";
import { clearCommittedOutbox, deleteOutboxCommand } from "../offline/idb";
import { checkCommandStatusOnServer, flushOutboxQueue } from "../offline/syncEngine";

interface OutboxMonitorViewProps {
  session: AuthSession;
  items: OutboxCommand[];
  simulatedOffline: boolean;
  onRefresh: () => Promise<void>;
}

const BADGE_MAP: Record<OutboxCommand["status"], string> = {
  QUEUED: "bg-amber-100 text-amber-900 border-amber-300",
  SYNCING: "bg-blue-100 text-blue-900 border-blue-300",
  COMMITTED: "bg-emerald-100 text-emerald-900 border-emerald-300",
  CONFLICT_409: "bg-rose-100 text-rose-900 border-rose-300",
  ERROR_4XX: "bg-rose-100 text-rose-900 border-rose-300",
  RETRY_WAIT: "bg-orange-100 text-orange-900 border-orange-300",
};

export const OutboxMonitorView: React.FC<OutboxMonitorViewProps> = ({
  session,
  items,
  simulatedOffline,
  onRefresh,
}) => {
  const [flushing, setFlushing] = useState(false);
  const [probeResult, setProbeResult] = useState<Record<string, unknown> | null>(null);

  const pendingCount = items.filter((i) => i.status === "QUEUED" || i.status === "RETRY_WAIT").length;

  const handleFlush = async () => {
    setFlushing(true);
    try {
      await flushOutboxQueue(session.access_token, simulatedOffline);
      await onRefresh();
    } finally {
      setFlushing(false);
    }
  };

  const handleClearCommitted = async () => {
    await clearCommittedOutbox();
    await onRefresh();
  };

  const handleProbe = async (cmdId: string) => {
    try {
      const res = await checkCommandStatusOnServer(cmdId, session.access_token);
      setProbeResult(res);
    } catch (err) {
      setProbeResult({ error: err instanceof Error ? err.message : String(err) });
    }
  };

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border border-slate-200 p-4 flex flex-wrap items-center justify-between gap-3 shadow-sm">
        <div>
          <h2 className="font-bold text-slate-900 text-base">
            Cola Local IndexedDB (Outbox Idempotente)
          </h2>
          <p className="text-xs text-slate-500">
            {items.length} comandos en dispositivo · <strong>{pendingCount}</strong> pendientes de
            sincronización · Reconciliación automática vía <code>/api/v1/sync/commands/&#123;id&#125;</code>
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={handleFlush}
            disabled={flushing || simulatedOffline || pendingCount === 0}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-emerald-800 hover:bg-emerald-700 disabled:opacity-50 text-white text-xs font-bold"
          >
            <CloudUpload className={`w-4 h-4 ${flushing ? "animate-bounce" : ""}`} />
            Sincronizar ahora ({pendingCount})
          </button>
          <button
            onClick={handleClearCommitted}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-300 hover:bg-slate-100 text-slate-700 text-xs font-semibold"
          >
            <Trash2 className="w-3.5 h-3.5" />
            Limpiar confirmados
          </button>
        </div>
      </div>

      {probeResult && (
        <div className="bg-slate-900 text-emerald-200 rounded-xl p-4 text-xs font-mono overflow-x-auto">
          <div className="flex justify-between items-center mb-2 text-slate-400">
            <span>Respuesta /api/v1/sync/commands/&#123;client_command_id&#125;</span>
            <button onClick={() => setProbeResult(null)} className="text-white hover:underline">
              Cerrar
            </button>
          </div>
          <pre>{JSON.stringify(probeResult, null, 2)}</pre>
        </div>
      )}

      {items.length === 0 ? (
        <div className="bg-white rounded-xl border border-dashed border-slate-300 p-10 text-center text-slate-500 text-sm">
          No hay comandos registrados en IndexedDB. Captura una cosecha, labor cultural o camión en la
          pestaña <strong>Tablet Campo</strong> (incluso en Modo Offline Simulado).
        </div>
      ) : (
        <div className="space-y-2.5">
          {items.map((item) => (
            <div
              key={item.client_command_id}
              className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm space-y-2"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span
                      className={`px-2 py-0.5 rounded-full text-[11px] font-bold border ${
                        BADGE_MAP[item.status]
                      }`}
                    >
                      {item.status}
                    </span>
                    <span className="font-bold text-sm text-slate-900">{item.label}</span>
                  </div>
                  <div className="text-[11px] text-slate-500 font-mono mt-1">
                    cmd: {item.client_command_id} · {item.method} {item.endpoint} · intentos:{" "}
                    {item.attempts}
                  </div>
                </div>

                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => handleProbe(item.client_command_id)}
                    disabled={simulatedOffline}
                    className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-slate-300 hover:bg-slate-50 text-[11px] font-semibold"
                    title="Consultar estado en servidor"
                  >
                    <Search className="w-3.5 h-3.5" />
                    Verificar ACK
                  </button>
                  <button
                    onClick={async () => {
                      await deleteOutboxCommand(item.client_command_id);
                      await onRefresh();
                    }}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50"
                    title="Eliminar de cola local"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>

              {item.last_error && (
                <div className="flex items-center gap-1.5 text-xs text-rose-800 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">
                  <AlertOctagon className="w-4 h-4 shrink-0" />
                  <span>{item.last_error}</span>
                </div>
              )}

              {item.server_ack && (
                <details className="text-xs">
                  <summary className="cursor-pointer text-emerald-700 font-semibold flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    Ver ACK confirmado del servidor
                  </summary>
                  <pre className="mt-1.5 bg-slate-900 text-emerald-200 p-3 rounded-lg overflow-x-auto text-[11px]">
                    {JSON.stringify(item.server_ack, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
