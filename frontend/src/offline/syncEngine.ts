import { ApiError, apiRequest } from "../api/client";
import type { OutboxCommand } from "../types";
import { listOutboxCommands, putOutboxCommand } from "./idb";

export function generateCommandId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  // Fallback RFC-4122 v4
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (ch) => {
    const r = (Math.random() * 16) | 0;
    const v = ch === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export async function enqueueOfflineCommand(input: {
  command_kind: OutboxCommand["command_kind"];
  endpoint: string;
  label: string;
  payload: Record<string, unknown>;
}): Promise<OutboxCommand> {
  const client_command_id = generateCommandId();
  const now = new Date().toISOString();
  const cmd: OutboxCommand = {
    client_command_id,
    command_kind: input.command_kind,
    endpoint: input.endpoint,
    method: "POST",
    label: input.label,
    payload: {
      ...input.payload,
      client_command_id,
    },
    status: "QUEUED",
    attempts: 0,
    created_at: now,
    updated_at: now,
    server_ack: null,
    last_error: null,
  };
  await putOutboxCommand(cmd);
  return cmd;
}

export async function checkCommandStatusOnServer(
  clientCommandId: string,
  token: string
): Promise<Record<string, unknown>> {
  return apiRequest<Record<string, unknown>>(`/api/v1/sync/commands/${clientCommandId}`, {
    method: "GET",
    token,
  });
}

export async function syncSingleCommand(
  cmd: OutboxCommand,
  token: string,
  simulatedOffline: boolean
): Promise<OutboxCommand> {
  if (simulatedOffline || !navigator.onLine) {
    return cmd;
  }

  const working: OutboxCommand = {
    ...cmd,
    status: "SYNCING",
    attempts: cmd.attempts + 1,
    updated_at: new Date().toISOString(),
  };
  await putOutboxCommand(working);

  // Si es reintento (attempts > 1), reconciliar primero el ACK en /api/v1/sync/commands/{id}
  if (working.attempts > 1) {
    try {
      const probe = await checkCommandStatusOnServer(working.client_command_id, token);
      if (probe.status === "COMMITTED") {
        const confirmed: OutboxCommand = {
          ...working,
          status: "COMMITTED",
          server_ack: (probe.committed_ack as Record<string, unknown>) || probe,
          last_error: null,
          updated_at: new Date().toISOString(),
        };
        await putOutboxCommand(confirmed);
        return confirmed;
      }
    } catch {
      // Si falla la sonda por red, seguimos con el manejo de error de red
    }
  }

  try {
    const ack = await apiRequest<Record<string, unknown>>(working.endpoint, {
      method: working.method,
      token,
      body: working.payload,
    });
    const committed: OutboxCommand = {
      ...working,
      status: "COMMITTED",
      server_ack: ack,
      last_error: null,
      updated_at: new Date().toISOString(),
    };
    await putOutboxCommand(committed);
    return committed;
  } catch (err) {
    if (err instanceof ApiError) {
      const nextStatus: OutboxCommand["status"] =
        err.status === 409 ? "CONFLICT_409" : err.status >= 400 && err.status < 500 ? "ERROR_4XX" : "RETRY_WAIT";
      const failed: OutboxCommand = {
        ...working,
        status: nextStatus,
        last_error: `HTTP ${err.status}: ${err.message}`,
        updated_at: new Date().toISOString(),
      };
      await putOutboxCommand(failed);
      return failed;
    }

    const offlineRetry: OutboxCommand = {
      ...working,
      status: "RETRY_WAIT",
      last_error: err instanceof Error ? err.message : "Sin conexión de red; reintento pendiente.",
      updated_at: new Date().toISOString(),
    };
    await putOutboxCommand(offlineRetry);
    return offlineRetry;
  }
}

export async function flushOutboxQueue(
  token: string,
  simulatedOffline: boolean
): Promise<OutboxCommand[]> {
  const all = await listOutboxCommands();
  if (simulatedOffline || !navigator.onLine) {
    return all;
  }
  // Procesar FIFO (los más antiguos primero)
  const pending = [...all]
    .reverse()
    .filter((c) => c.status === "QUEUED" || c.status === "RETRY_WAIT");

  for (const item of pending) {
    await syncSingleCommand(item, token, simulatedOffline);
  }
  return listOutboxCommands();
}
