import React, { useCallback, useEffect, useState } from "react";
import {
  BarChart3,
  Building2,
  CloudOff,
  Database,
  LogOut,
  Smartphone,
  Sprout,
  Wifi,
  WifiOff,
} from "lucide-react";
import { apiRequest } from "./api/client";
import { ExecutiveFinanceView } from "./components/ExecutiveFinanceView";
import { FieldTabletView } from "./components/FieldTabletView";
import { LoginView } from "./components/LoginView";
import { OfficePanelView } from "./components/OfficePanelView";
import { OutboxMonitorView } from "./components/OutboxMonitorView";
import {
  listOutboxCommands,
  loadCachedCatalogs,
  loadEligibilitySnapshot,
  saveCachedCatalogs,
  saveEligibilitySnapshot,
} from "./offline/idb";
import { flushOutboxQueue } from "./offline/syncEngine";
import type {
  AuthSession,
  CachedCatalogs,
  EligibilitySnapshot,
  EmpresaItem,
  HealthStatus,
  LoteCatalogo,
  OutboxCommand,
  UnidadOperativa,
} from "./types";

const SESSION_KEY = "agro_erp_berries_session_v2";

type MainTab = "tablet" | "outbox" | "office" | "finance";

export function App() {
  const [session, setSession] = useState<AuthSession | null>(() => {
    try {
      const raw = localStorage.getItem(SESSION_KEY);
      return raw ? (JSON.parse(raw) as AuthSession) : null;
    } catch {
      return null;
    }
  });
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [navigatorOnline, setNavigatorOnline] = useState<boolean>(
    typeof navigator !== "undefined" ? navigator.onLine : true
  );
  const [simulatedOffline, setSimulatedOffline] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<MainTab>("tablet");

  const [snapshot, setSnapshot] = useState<EligibilitySnapshot | null>(null);
  const [catalogs, setCatalogs] = useState<CachedCatalogs | null>(null);
  const [outbox, setOutbox] = useState<OutboxCommand[]>([]);

  const effectiveOnline = navigatorOnline && !simulatedOffline;

  const reloadLocalState = useCallback(async () => {
    const [snap, cat, ob] = await Promise.all([
      loadEligibilitySnapshot(),
      loadCachedCatalogs(),
      listOutboxCommands(),
    ]);
    setSnapshot(snap);
    setCatalogs(cat);
    setOutbox(ob);
  }, []);

  const refreshHealth = useCallback(async () => {
    try {
      const h = await apiRequest<HealthStatus>("/api/v1/health");
      setHealth(h);
    } catch {
      // Silencioso en modo offline
    }
  }, []);

  const syncSnapshotAndCatalogs = useCallback(async () => {
    if (!session || simulatedOffline || !navigator.onLine) return;

    try {
      const elig = await apiRequest<Omit<EligibilitySnapshot, "id">>(
        "/api/v1/campo/eligibility/daily",
        { token: session.access_token }
      );
      const savedSnap: EligibilitySnapshot = { id: "current", ...elig };
      await saveEligibilitySnapshot(savedSnap);
      setSnapshot(savedSnap);
    } catch {
      // Usuario sin permiso campo.elegibilidad.leer mantiene snapshot previo si existía
    }

    try {
      const [catOp, emps, uos] = await Promise.all([
        apiRequest<{ lotes: LoteCatalogo[] }>("/api/v1/catalogos/operacion", {
          token: session.access_token,
        }),
        apiRequest<EmpresaItem[] | { empresas?: EmpresaItem[]; items?: EmpresaItem[] }>(
          "/api/v1/org/empresas",
          { token: session.access_token }
        ),
        apiRequest<UnidadOperativa[] | { unidades?: UnidadOperativa[]; items?: UnidadOperativa[] }>(
          "/api/v1/org/unidades",
          { token: session.access_token }
        ),
      ]);

      const empresasList: EmpresaItem[] = Array.isArray(emps)
        ? emps
        : emps.empresas ?? emps.items ?? [];
      const unidadesList: UnidadOperativa[] = Array.isArray(uos)
        ? uos
        : uos.unidades ?? uos.items ?? [];

      const cached: CachedCatalogs = {
        id: "current",
        synced_at: new Date().toISOString(),
        lotes: catOp.lotes ?? [],
        empresas: empresasList,
        unidades: unidadesList,
      };
      await saveCachedCatalogs(cached);
      setCatalogs(cached);
    } catch {
      // Mantiene cache previo en IndexedDB si hay fallo de red
    }
  }, [session, simulatedOffline]);

  useEffect(() => {
    void refreshHealth();
    void reloadLocalState();

    const onOnline = () => setNavigatorOnline(true);
    const onOffline = () => setNavigatorOnline(false);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, [refreshHealth, reloadLocalState]);

  useEffect(() => {
    if (!session) return;
    if (effectiveOnline) {
      void syncSnapshotAndCatalogs();
      void flushOutboxQueue(session.access_token, simulatedOffline).then(setOutbox);
    }
  }, [session, effectiveOnline, simulatedOffline, syncSnapshotAndCatalogs]);

  const handleLogin = (newSession: AuthSession) => {
    localStorage.setItem(SESSION_KEY, JSON.stringify(newSession));
    setSession(newSession);
  };

  const handleLogout = () => {
    localStorage.removeItem(SESSION_KEY);
    setSession(null);
  };

  if (!session) {
    return (
      <LoginView health={health} online={effectiveOnline} onAuthenticated={handleLogin} />
    );
  }

  const pendingOutbox = outbox.filter(
    (c) => c.status === "QUEUED" || c.status === "RETRY_WAIT"
  ).length;

  return (
    <div className="min-h-screen bg-slate-100 flex flex-col">
      <header className="bg-emerald-950 text-white shadow-md sticky top-0 z-30">
        <div className="max-w-6xl mx-auto px-4 py-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-rose-600 flex items-center justify-center shadow">
              <Sprout className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="font-bold text-sm sm:text-base leading-tight">
                AGRO-ERP Berries v2
              </div>
              <div className="text-[11px] text-emerald-200">
                {session.usuario.nombre_completo} (<code>{session.usuario.username}</code>)
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* Simulador de Modo Offline para pruebas reales de campo */}
            <button
              onClick={() => setSimulatedOffline((prev) => !prev)}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold transition border ${
                simulatedOffline
                  ? "bg-amber-400 text-slate-950 border-amber-300"
                  : effectiveOnline
                  ? "bg-emerald-900 text-emerald-100 border-emerald-700 hover:bg-emerald-800"
                  : "bg-rose-600 text-white border-rose-500"
              }`}
              title="Alternar simulación de modo sin señal"
            >
              {simulatedOffline ? (
                <>
                  <CloudOff className="w-3.5 h-3.5" />
                  Offline Simulado
                </>
              ) : effectiveOnline ? (
                <>
                  <Wifi className="w-3.5 h-3.5" />
                  En Línea
                </>
              ) : (
                <>
                  <WifiOff className="w-3.5 h-3.5" />
                  Sin Señal
                </>
              )}
            </button>

            <button
              onClick={handleLogout}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-emerald-900 hover:bg-emerald-800 text-xs font-semibold"
            >
              <LogOut className="w-3.5 h-3.5" />
              Salir
            </button>
          </div>
        </div>

        {/* Barra de navegación principal */}
        <div className="bg-emerald-900/90 border-t border-emerald-800">
          <div className="max-w-6xl mx-auto px-4 flex gap-1 overflow-x-auto">
            <button
              onClick={() => setActiveTab("tablet")}
              className={`flex items-center gap-2 px-4 py-2.5 text-xs sm:text-sm font-bold border-b-2 transition whitespace-nowrap ${
                activeTab === "tablet"
                  ? "border-amber-400 text-white"
                  : "border-transparent text-emerald-200 hover:text-white"
              }`}
            >
              <Smartphone className="w-4 h-4" />
              Tablet Campo
            </button>
            <button
              onClick={() => setActiveTab("outbox")}
              className={`flex items-center gap-2 px-4 py-2.5 text-xs sm:text-sm font-bold border-b-2 transition whitespace-nowrap ${
                activeTab === "outbox"
                  ? "border-amber-400 text-white"
                  : "border-transparent text-emerald-200 hover:text-white"
              }`}
            >
              <Database className="w-4 h-4" />
              Cola Offline (IndexedDB)
              {pendingOutbox > 0 && (
                <span className="px-2 py-0.5 rounded-full bg-amber-400 text-slate-950 text-[10px] font-extrabold">
                  {pendingOutbox}
                </span>
              )}
            </button>
            <button
              onClick={() => setActiveTab("office")}
              className={`flex items-center gap-2 px-4 py-2.5 text-xs sm:text-sm font-bold border-b-2 transition whitespace-nowrap ${
                activeTab === "office"
                  ? "border-amber-400 text-white"
                  : "border-transparent text-emerald-200 hover:text-white"
              }`}
            >
              <Building2 className="w-4 h-4" />
              Panel Oficina &amp; Merqry
            </button>
            <button
              onClick={() => setActiveTab("finance")}
              className={`flex items-center gap-2 px-4 py-2.5 text-xs sm:text-sm font-bold border-b-2 transition whitespace-nowrap ${
                activeTab === "finance"
                  ? "border-amber-400 text-white"
                  : "border-transparent text-emerald-200 hover:text-white"
              }`}
            >
              <BarChart3 className="w-4 h-4" />
              Finanzas &amp; Auditoría
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl w-full mx-auto px-4 py-5 flex-1">
        {activeTab === "tablet" && (
          <FieldTabletView
            session={session}
            snapshot={snapshot}
            catalogs={catalogs}
            simulatedOffline={simulatedOffline}
            onRefreshSnapshot={syncSnapshotAndCatalogs}
            onOutboxUpdated={reloadLocalState}
          />
        )}
        {activeTab === "outbox" && (
          <OutboxMonitorView
            session={session}
            items={outbox}
            simulatedOffline={simulatedOffline}
            onRefresh={reloadLocalState}
          />
        )}
        {activeTab === "office" && <OfficePanelView session={session} catalogs={catalogs} />}
        {activeTab === "finance" && (
          <ExecutiveFinanceView session={session} catalogs={catalogs} />
        )}
      </main>
    </div>
  );
}

export default App;
