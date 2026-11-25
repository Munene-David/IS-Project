/**
 * Shared types & formatting helpers for the date/time picker field.
 * Used by both the native (iOS/Android) and web implementations.
 */

export interface DateTimePickerFieldProps {
  /** Label shown above the field. */
  label: string;
  /** Which picker to show. */
  mode: 'date' | 'time';
  /** Current value (null = not set). */
  value: Date | null;
  /** Called with the picked value, or null when cleared. */
  onChange: (value: Date | null) => void;
  /** Shown inside the field when no value is set. */
  placeholder?: string;
  /** Earliest selectable date/time. */
  minimumDate?: Date;
  /** Helper text below the field. */
  hint?: string;
}

/** Local (not UTC) YYYY-MM-DD, e.g. "2026-11-25". */
export function formatDateForApi(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

/** Local 24-hour time with seconds, e.g. "09:30:00". */
export function formatTimeForApi(date: Date): string {
  const h = String(date.getHours()).padStart(2, '0');
  const m = String(date.getMinutes()).padStart(2, '0');
  return `${h}:${m}:00`;
}

/** Value shown inside the field. */
export function formatDisplayValue(
  mode: 'date' | 'time',
  value: Date | null,
  placeholder?: string
): string {
  if (!value) {
    return placeholder ?? (mode === 'date' ? 'Select date' : 'Select time');
  }
  if (mode === 'date') {
    return value.toLocaleDateString(undefined, {
      weekday: 'short',
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  }
  return value.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

/** Parse a web <input type="date|time"> string back into a local Date. */
export function parseInputValue(
  mode: 'date' | 'time',
  raw: string,
  currentValue: Date | null
): Date | null {
  if (!raw) return null;
  if (mode === 'date') {
    const [y, m, d] = raw.split('-').map(Number);
    if (!y || !m || !d) return null;
    // Midday avoids DST edge cases; only Y/M/D are used by the API formatter.
    return new Date(y, m - 1, d, 12, 0, 0);
  }
  const [h, min] = raw.split(':').map(Number);
  if (Number.isNaN(h) || Number.isNaN(min)) return null;
  const base = currentValue ?? new Date();
  return new Date(base.getFullYear(), base.getMonth(), base.getDate(), h, min, 0);
}
