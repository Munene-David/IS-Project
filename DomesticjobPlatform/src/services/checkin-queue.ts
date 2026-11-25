/**
 * Offline check-in queue.
 *
 * When a student submits their start code without connectivity, the
 * check-in (with the location captured at that moment) is stored locally
 * and replayed later with `late_sync: true` and the ORIGINAL device_time,
 * so the server can flag it as a late sync.
 *
 * Entries are removed once the server returns a definitive response
 * (any HTTP status).  Network failures keep the entry for the next sync.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import { api, CheckinPayload } from './api';

const STORAGE_KEY = '@domesticjobs/checkin_queue';

export interface QueuedCheckin {
  /** Local id (timestamp-based). */
  id: string;
  task_id: number;
  payload: CheckinPayload;
  queued_at: string;
}

export async function getQueuedCheckins(): Promise<QueuedCheckin[]> {
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as QueuedCheckin[]) : [];
  } catch {
    return [];
  }
}

/** Queue a check-in that could not be submitted right now. */
export async function queueCheckin(
  taskId: number,
  payload: CheckinPayload,
): Promise<void> {
  const queue = await getQueuedCheckins();
  queue.push({
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    task_id: taskId,
    payload,
    queued_at: new Date().toISOString(),
  });
  await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(queue));
}

export async function clearQueuedCheckins(): Promise<void> {
  await AsyncStorage.removeItem(STORAGE_KEY);
}

/**
 * Replay queued check-ins.  Returns how many synced successfully and how
 * many are still waiting (kept only on network errors).
 */
export async function syncQueuedCheckins(): Promise<{
  synced: number;
  remaining: number;
}> {
  const queue = await getQueuedCheckins();
  const remaining: QueuedCheckin[] = [];
  let synced = 0;

  for (const entry of queue) {
    try {
      const res = await api.tasks.checkin(entry.task_id, {
        ...entry.payload,
        late_sync: true,
      });
      if (res.ok) {
        synced += 1;
      } else {
        // Definitive server response (wrong code, task moved on, …):
        // retrying won't help — drop it, the student will see the state
        // on the task screen.
        synced += 0;
      }
    } catch {
      // Network still down — keep for the next attempt.
      remaining.push(entry);
    }
  }

  await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(remaining));
  return { synced, remaining: remaining.length };
}
