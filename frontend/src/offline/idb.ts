import type { CachedCatalogs, EligibilitySnapshot, OutboxCommand } from "../types";

const DB_NAME = "agro_erp_berries_offline_v2";
const DB_VERSION = 1;

const STORE_OUTBOX = "command_outbox";
const STORE_ELIGIBILITY = "eligible_snapshot";
const STORE_CATALOGS = "catalog_cache";

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_OUTBOX)) {
        const store = db.createObjectStore(STORE_OUTBOX, { keyPath: "client_command_id" });
        store.createIndex("by_created_at", "created_at", { unique: false });
        store.createIndex("by_status", "status", { unique: false });
      }
      if (!db.objectStoreNames.contains(STORE_ELIGIBILITY)) {
        db.createObjectStore(STORE_ELIGIBILITY, { keyPath: "id" });
      }
      if (!db.objectStoreNames.contains(STORE_CATALOGS)) {
        db.createObjectStore(STORE_CATALOGS, { keyPath: "id" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function txDone<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function putOutboxCommand(cmd: OutboxCommand): Promise<void> {
  const db = await openDB();
  const tx = db.transaction(STORE_OUTBOX, "readwrite");
  await txDone(tx.objectStore(STORE_OUTBOX).put(cmd));
  db.close();
}

export async function listOutboxCommands(): Promise<OutboxCommand[]> {
  const db = await openDB();
  const tx = db.transaction(STORE_OUTBOX, "readonly");
  const all = await txDone(tx.objectStore(STORE_OUTBOX).getAll());
  db.close();
  return (all as OutboxCommand[]).sort((a, b) => b.created_at.localeCompare(a.created_at));
}

export async function deleteOutboxCommand(clientCommandId: string): Promise<void> {
  const db = await openDB();
  const tx = db.transaction(STORE_OUTBOX, "readwrite");
  await txDone(tx.objectStore(STORE_OUTBOX).delete(clientCommandId));
  db.close();
}

export async function clearCommittedOutbox(): Promise<void> {
  const items = await listOutboxCommands();
  const db = await openDB();
  const tx = db.transaction(STORE_OUTBOX, "readwrite");
  const store = tx.objectStore(STORE_OUTBOX);
  for (const item of items) {
    if (item.status === "COMMITTED") {
      store.delete(item.client_command_id);
    }
  }
  await new Promise<void>((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}

export async function saveEligibilitySnapshot(snap: EligibilitySnapshot): Promise<void> {
  const db = await openDB();
  const tx = db.transaction(STORE_ELIGIBILITY, "readwrite");
  await txDone(tx.objectStore(STORE_ELIGIBILITY).put(snap));
  db.close();
}

export async function loadEligibilitySnapshot(): Promise<EligibilitySnapshot | null> {
  const db = await openDB();
  const tx = db.transaction(STORE_ELIGIBILITY, "readonly");
  const res = await txDone(tx.objectStore(STORE_ELIGIBILITY).get("current"));
  db.close();
  return (res as EligibilitySnapshot | undefined) ?? null;
}

export async function saveCachedCatalogs(cat: CachedCatalogs): Promise<void> {
  const db = await openDB();
  const tx = db.transaction(STORE_CATALOGS, "readwrite");
  await txDone(tx.objectStore(STORE_CATALOGS).put(cat));
  db.close();
}

export async function loadCachedCatalogs(): Promise<CachedCatalogs | null> {
  const db = await openDB();
  const tx = db.transaction(STORE_CATALOGS, "readonly");
  const res = await txDone(tx.objectStore(STORE_CATALOGS).get("current"));
  db.close();
  return (res as CachedCatalogs | undefined) ?? null;
}
