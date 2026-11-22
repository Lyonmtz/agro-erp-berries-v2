import React, { useState } from "react";
import { ShieldCheck, Lock, Sprout, Wifi, WifiOff } from "lucide-react";
import { ApiError, apiRequest } from "../api/client";
import type { AuthSession, HealthStatus } from "../types";

interface LoginViewProps {
  health: HealthStatus | null;
  online: boolean;
  onAuthenticated: (session: AuthSession) => void;
}

const DEV_PROFILES = [
  { label: "Dirección General (L4 Global)", u: "admin.dir", p: "AdminBerries2026!" },
  { label: "Jefatura RH NFA (L3)", u: "rh.nfa", p: "RhNfa2026!" },
  { label: "Supervisor Frambuesa NFA (L2)", u: "sup.framb", p: "SupFramb2026!" },
  { label: "Supervisor Arándano BIO (L2)", u: "sup.bio", p: "SupBio2026!" },
];

export const LoginView: React.FC<LoginViewProps> = ({ health, online, onAuthenticated }) => {
  const [username, setUsername] = useState("sup.framb");
  const [password, setPassword] = useState("SupFramb2026!");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const session = await apiRequest<AuthSession>("/api/v1/auth/login", {
        method: "POST",
        body: { username: username.trim(), password },
      });
      onAuthenticated(session);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo conectar con la API de autenticación.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-emerald-950 via-emerald-900 to-slate-900 flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl overflow-hidden border border-emerald-800/30">
        <div className="bg-emerald-900 text-white px-6 py-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-10 h-10 rounded-xl bg-rose-600 flex items-center justify-center shadow">
                <Sprout className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-lg font-bold tracking-tight">AGRO-ERP Berries v2</h1>
                <p className="text-xs text-emerald-200">PWA Offline-First · NFA &amp; BIO</p>
              </div>
            </div>
            <span
              className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold ${
                online ? "bg-emerald-800 text-emerald-100" : "bg-amber-500 text-slate-950"
              }`}
            >
              {online ? <Wifi className="w-3.5 h-3.5" /> : <WifiOff className="w-3.5 h-3.5" />}
              {online ? "En línea" : "Sin red"}
            </span>
          </div>

          {health && (
            <div className="mt-4 grid grid-cols-2 gap-2 text-[11px] bg-emerald-950/60 rounded-lg p-2.5 border border-emerald-700/50">
              <div>
                <span className="text-emerald-300">Entorno BD:</span>{" "}
                <strong className="text-white">{health.db_environment}</strong>
              </div>
              <div>
                <span className="text-emerald-300">Merqry:</span>{" "}
                <strong className="text-emerald-200">{health.merqry_mode}</strong>
              </div>
              <div className="col-span-2 flex items-center gap-1.5 text-emerald-200">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                <span>
                  merqry_writer:{" "}
                  <strong className="text-white">
                    {health.merqry_write_enabled ? "HABILITADO" : "APAGADO (fail-closed)"}
                  </strong>
                </span>
              </div>
            </div>
          )}
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-600 uppercase mb-1">
              Usuario
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoComplete="username"
              className="w-full rounded-lg border border-slate-300 px-3.5 py-2.5 text-sm focus:border-emerald-600 focus:ring-2 focus:ring-emerald-200 outline-none"
              placeholder="Ej. sup.framb"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 uppercase mb-1">
              Contraseña
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              className="w-full rounded-lg border border-slate-300 px-3.5 py-2.5 text-sm focus:border-emerald-600 focus:ring-2 focus:ring-emerald-200 outline-none"
            />
          </div>

          {error && (
            <div className="rounded-lg bg-rose-50 border border-rose-200 text-rose-800 px-3.5 py-2.5 text-xs font-medium">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-emerald-800 hover:bg-emerald-700 disabled:opacity-50 text-white font-bold py-3 rounded-xl shadow flex items-center justify-center gap-2 transition"
          >
            <Lock className="w-4 h-4" />
            {loading ? "Validando credenciales..." : "Iniciar Sesión Segura"}
          </button>

          <div className="pt-3 border-t border-slate-100">
            <p className="text-[11px] font-semibold text-slate-500 uppercase mb-2">
              Perfiles rápidos de desarrollo (RBAC)
            </p>
            <div className="grid grid-cols-2 gap-1.5">
              {DEV_PROFILES.map((prof) => (
                <button
                  key={prof.u}
                  type="button"
                  onClick={() => {
                    setUsername(prof.u);
                    setPassword(prof.p);
                  }}
                  className="text-left px-2.5 py-1.5 rounded-lg border border-slate-200 hover:border-emerald-500 hover:bg-emerald-50 transition text-[11px]"
                >
                  <div className="font-bold text-slate-800">{prof.u}</div>
                  <div className="text-slate-500 truncate">{prof.label}</div>
                </button>
              ))}
            </div>
          </div>
        </form>
      </div>
    </div>
  );
};
