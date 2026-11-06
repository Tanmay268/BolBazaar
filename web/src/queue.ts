/**
 * Device-side offline queue. A recording made without connectivity is stored in IndexedDB with its
 * Idempotency-Key, then replayed through POST /captures when the network returns. Because the key
 * is stored with the audio, a replay that races a slow first attempt can never create a duplicate.
 */
import { ApiFailure, api } from "./api";

export interface PendingCapture {
  key: string;
  blob: Blob;
  language: string;
  capturedAt: string;
  createdAt: number;
}

const DB = "fieldforce";
const STORE = "pending";

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: "key" });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function tx<T>(mode: IDBTransactionMode, run: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await open();
  return new Promise<T>((resolve, reject) => {
    const req = run(db.transaction(STORE, mode).objectStore(STORE));
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export const queue = {
  async add(item: PendingCapture): Promise<void> { await tx("readwrite", (s) => s.put(item)); },
  async all(): Promise<PendingCapture[]> {
    try { return ((await tx("readonly", (s) => s.getAll())) as PendingCapture[]).sort((a, b) => a.createdAt - b.createdAt); }
    catch { return []; }
  },
  async remove(key: string): Promise<void> { await tx("readwrite", (s) => s.delete(key)); },
  async count(): Promise<number> { try { return await tx("readonly", (s) => s.count()); } catch { return 0; } },
};

let flushing = false;

/** Replays queued captures in order. Stops at the first network failure; drops items the server rejects for good. */
export async function flushQueue(): Promise<{ sent: number; left: number }> {
  if (flushing) return { sent: 0, left: await queue.count() };
  flushing = true;
  let sent = 0;
  try {
    for (const item of await queue.all()) {
      try {
        await api.createCapture({ audio: item.blob, language: item.language, key: item.key, capturedAt: item.capturedAt });
        await queue.remove(item.key);
        sent++;
      } catch (error) {
        if (error instanceof ApiFailure && error.isNetwork) break;
        // 5xx / provider outage: keep it for the next attempt. 4xx other than rate-limit won't ever succeed.
        if (error instanceof ApiFailure && error.status >= 400 && error.status < 500 && error.status !== 429 && error.status !== 409) {
          await queue.remove(item.key);
          continue;
        }
        if (error instanceof ApiFailure && error.status === 409) { await queue.remove(item.key); continue; }
        break;
      }
    }
  } finally {
    flushing = false;
  }
  return { sent, left: await queue.count() };
}
