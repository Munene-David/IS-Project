import { Platform } from 'react-native';

// ─────────────────────────────────────────────────────────────
// LAN IP is set in .env as EXPO_PUBLIC_LAN_IP.
// Change it there whenever your Wi-Fi IP changes — no code edit needed.
//
// How to find your IP:
//   Windows : ipconfig  → Wi-Fi IPv4 Address
//   Mac/Linux: ifconfig → en0 inet
// ─────────────────────────────────────────────────────────────
const LAN_IP = process.env.EXPO_PUBLIC_LAN_IP ?? '192.168.0.34';

export const API_BASE_URL = Platform.select({
  android: `http://${LAN_IP}:8000/api`,
  ios: `http://${LAN_IP}:8000/api`,
  default: 'http://localhost:8000/api', // web browser
});

let authToken: string | null = null;

export const setAuthToken = (token: string | null) => {
  authToken = token;
};

export const getAuthToken = () => authToken;

// ---------------------------------------------------------------------------
// Geolocation types
// ---------------------------------------------------------------------------

/** A one-shot device location snapshot (captured only at check-in events). */
export interface LocationSnapshot {
  lat: number;
  lng: number;
  accuracy_m: number | null;
  /** ISO timestamp from the device when the position was captured. */
  device_time: string;
  /** True when the OS reports the fix as mocked/simulated (Android). */
  mock_location: boolean;
}

/** Body for the geolocation-verified check-in. */
export interface CheckinPayload extends Partial<LocationSnapshot> {
  start_code: string;
  /** True when re-submitting a better GPS fix after a flagged check-in. */
  retry?: boolean;
  /** True when syncing a check-in that was queued while offline. */
  late_sync?: boolean;
  device_info?: Record<string, unknown>;
}

export interface GeoConsentInfo {
  required: boolean;
  version: string;
  text: string;
  consented: boolean;
}

export interface PlaceResult {
  label: string;
  lat: number;
  lng: number;
}

export interface CheckinSummary {
  arrived_at: string;
  result: string;
  location_verified: boolean;
  flagged: boolean;
  flags: { mock_location: boolean; late_sync: boolean; impossible_jump: boolean };
}

export interface LocationAuditData {
  task: {
    id: number;
    title: string;
    status: string;
    household_owner: string;
    assigned_student: string | null;
    location_address: string;
    location_landmark: string | null;
    location_lat: string | null;
    location_lng: string | null;
    geofence_radius_m: number;
    scheduled_date: string | null;
    scheduled_time: string | null;
  };
  checkins: {
    id: number;
    student_username: string;
    type: string;
    lat: string | null;
    lng: string | null;
    accuracy_m: number | null;
    distance_m: number | null;
    device_time: string | null;
    server_time: string;
    time_skew_seconds: number | null;
    result: string;
    mock_location_flag: boolean;
    late_sync_flag: boolean;
    impossible_jump_flag: boolean;
    device_info: Record<string, any>;
    anonymised_at: string | null;
  }[];
  dispute: any | null;
  messages: {
    id: number;
    sender_username: string;
    receiver_username: string;
    content: string;
    timestamp: string;
  }[];
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };

  if (authToken) {
    headers['Authorization'] = `Token ${authToken}`;
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  const contentType = response.headers.get('content-type');
  let data: any = null;
  if (contentType && contentType.includes('application/json')) {
    data = await response.json();
  } else {
    data = await response.text();
  }

  if (!response.ok) {
    const errorMsg =
      (typeof data === 'object' && (data?.error || data?.detail || JSON.stringify(data))) ||
      'Request failed';
    throw new Error(errorMsg);
  }

  return data as T;
}

/**
 * Non-throwing request variant.  Check-in needs the structured body of 4xx
 * responses (result: WRONG_CODE / LOCATION_DENIED / …) to branch on.
 */
async function requestRaw<T = any>(
  endpoint: string,
  options: RequestInit = {},
): Promise<{ ok: boolean; status: number; data: T }> {
  const url = `${API_BASE_URL}${endpoint}`;
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (authToken) {
    headers['Authorization'] = `Token ${authToken}`;
  }
  const response = await fetch(url, { ...options, headers });
  const contentType = response.headers.get('content-type');
  let data: any = null;
  if (contentType && contentType.includes('application/json')) {
    data = await response.json();
  } else {
    data = await response.text();
  }
  return { ok: response.ok, status: response.status, data };
}

/** Multipart/form-data request (file uploads). */
async function requestFormData<T>(endpoint: string, formData: FormData): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const headers: Record<string, string> = {};
  if (authToken) {
    headers['Authorization'] = `Token ${authToken}`;
  }
  const response = await fetch(url, {
    method: 'POST',
    headers,
    body: formData,
  });
  const contentType = response.headers.get('content-type');
  let data: any = null;
  if (contentType && contentType.includes('application/json')) {
    data = await response.json();
  } else {
    data = await response.text();
  }
  if (!response.ok) {
    const errorMsg =
      (typeof data === 'object' && (data?.error || data?.detail || JSON.stringify(data))) ||
      'Request failed';
    throw new Error(errorMsg);
  }
  return data as T;
}

export const api = {
  auth: {
    login: (identifier: string, password: string) =>
      request<{ token: string; user: any }>('/auth/login/', {
        method: 'POST',
        body: JSON.stringify({ username: identifier, password }),
      }),
    registerStudent: (payload: {
      username: string;
      email: string;
      password: string;
      first_name?: string;
      last_name?: string;
      phone_number: string;
      university_id: string;
      university_name: string;
    }) =>
      request<{ token: string; user: any; message: string }>('/auth/register/student/', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    registerHousehold: (payload: {
      username: string;
      email: string;
      password: string;
      first_name?: string;
      last_name?: string;
      phone_number: string;
      address: string;
      location_lat?: number;
      location_lng?: number;
    }) =>
      request<{ token: string; user: any; message: string }>('/auth/register/household/', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    me: () => request<any>('/auth/me/'),
  },

  priceGuide: {
    getAll: () => request<any[]>('/price-guide/'),
    getByCategory: (category: string) =>
      request<{ category: string; min_price: string; max_price: string; recommended_price: string }>(
        `/price-guide/${encodeURIComponent(category)}/`
      ),
  },

  tasks: {
    list: (params?: { category?: string; status?: string; search?: string; my_tasks?: boolean }) => {
      const query = new URLSearchParams();
      if (params?.category) query.append('category', params.category);
      if (params?.status) query.append('status', params.status);
      if (params?.search) query.append('search', params.search);
      if (params?.my_tasks) query.append('my_tasks', 'true');
      const q = query.toString();
      return request<any[]>(`/tasks/${q ? `?${q}` : ''}`);
    },
    get: (id: number) => request<any>(`/tasks/${id}/`),
    create: (payload: {
      title: string;
      description: string;
      category: string;
      posted_price: number | string;
      recommended_price?: number | string;
      location_address?: string;
      location_lat?: number;
      location_lng?: number;
      location_landmark?: string;
      geofence_radius_m?: number;
      location_pin_confirmed?: boolean;
      scheduled_date?: string;
      scheduled_time?: string;
    }) =>
      request<any>('/tasks/', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    delete: (taskId: number) =>
      request<any>(`/tasks/${taskId}/`, { method: 'DELETE' }),

    // --- Completion verification ---
    getStartCode: (taskId: number) =>
      request<{ start_code: string }>(`/tasks/${taskId}/start-code/`),
    /**
     * Geolocation-verified check-in.  Returns the raw response (never
     * throws) so the caller can branch on `data.result` for both 200s
     * (VERIFIED / flagged) and structured 400s (WRONG_CODE / LOCATION_DENIED
     * / FLAGGED_MOCK) and 403 consent_required.
     */
    checkin: (taskId: number, payload: CheckinPayload) =>
      requestRaw<any>(`/tasks/${taskId}/checkin/`, {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    studentComplete: (
      taskId: number,
      afterPhoto?: File,
      location?: LocationSnapshot,
    ) => {
      if (afterPhoto || location) {
        const form = new FormData();
        if (afterPhoto) form.append('after_photo', afterPhoto);
        if (location) {
          form.append('lat', String(location.lat));
          form.append('lng', String(location.lng));
          if (location.accuracy_m != null) {
            form.append('accuracy_m', String(location.accuracy_m));
          }
          form.append('device_time', location.device_time);
          form.append('mock_location', String(location.mock_location));
        }
        return requestFormData<any>(`/tasks/${taskId}/student-complete/`, form);
      }
      return request<any>(`/tasks/${taskId}/student-complete/`, { method: 'POST' });
    },
    confirmCompletion: (taskId: number) =>
      request<any>(`/tasks/${taskId}/confirm-completion/`, { method: 'POST' }),
    uploadBeforePhoto: (taskId: number, photo: File) => {
      const form = new FormData();
      form.append('before_photo', photo);
      return requestFormData<any>(`/tasks/${taskId}/upload-before-photo/`, form);
    },
    /** Admin-only location audit / dispute map view. */
    locationAudit: (taskId: number) =>
      request<LocationAuditData>(`/tasks/${taskId}/location-audit/`),

    // --- Disputes ---
    raiseDispute: (taskId: number, payload: { reason: string; description: string }) =>
      request<any>(`/tasks/${taskId}/dispute/`, {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    disputeResponse: (taskId: number, response: string) =>
      request<any>(`/tasks/${taskId}/dispute-response/`, {
        method: 'POST',
        body: JSON.stringify({ response }),
      }),
    disputeResolve: (taskId: number, payload: {
      outcome: 'full_refund' | 'partial_refund' | 'release';
      partial_refund_amount?: number;
      admin_notes?: string;
    }) =>
      request<any>(`/tasks/${taskId}/dispute-resolve/`, {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    disputeDetail: (taskId: number) => request<any>(`/tasks/${taskId}/dispute-detail/`),

    // --- Cancel with refund policy ---
    cancelTask: (taskId: number) =>
      request<any>(`/tasks/${taskId}/cancel/`, { method: 'POST' }),

    // --- Ledger & audit ---
    ledger: (taskId: number) => request<any[]>(`/tasks/${taskId}/ledger/`),
    auditLog: (taskId: number) => request<any[]>(`/tasks/${taskId}/audit-log/`),

    markComplete: (taskId: number) =>
      request<any>(`/tasks/${taskId}/complete/`, { method: 'POST' }),
    dispute: (taskId: number) =>
      request<any>(`/tasks/${taskId}/dispute/`, { method: 'POST' }),
    getMessages: (taskId: number) => request<any[]>(`/tasks/${taskId}/messages/`),
    sendMessage: (taskId: number, content: string, receiverId?: number) =>
      request<any>(`/tasks/${taskId}/messages/`, {
        method: 'POST',
        body: JSON.stringify({ content, receiver_id: receiverId }),
      }),
    // --- Broadcast-flow endpoints ---
    myRequests: () => request<any[]>('/tasks/my-requests/'),
    myRequestsHistory: () => request<any[]>('/tasks/my-requests/history/'),
    acceptRequest: (requestId: number) =>
      request<any>('/tasks/accept-request/', {
        method: 'POST',
        body: JSON.stringify({ request_id: requestId }),
      }),
    declineRequest: (requestId: number) =>
      request<any>('/tasks/decline-request/', {
        method: 'POST',
        body: JSON.stringify({ request_id: requestId }),
      }),
    ignoreRequest: (requestId: number) =>
      request<any>('/tasks/ignore-request/', {
        method: 'POST',
        body: JSON.stringify({ request_id: requestId }),
      }),
    confirmMatch: (taskId: number, phoneNumber: string) =>
      request<any>(`/tasks/${taskId}/confirm-match/`, {
        method: 'POST',
        body: JSON.stringify({ phone_number: phoneNumber }),
      }),
    cancelMatch: (taskId: number, blockStudent?: boolean) =>
      request<any>(`/tasks/${taskId}/cancel-match/`, {
        method: 'POST',
        body: JSON.stringify({ block_student: blockStudent || false }),
      }),
    rebroadcast: (taskId: number) =>
      request<any>(`/tasks/${taskId}/rebroadcast/`, { method: 'POST' }),
    studentCancel: (taskId: number) =>
      request<any>(`/tasks/${taskId}/student-cancel/`, { method: 'POST' }),
  },

  household: {
    getSettings: () =>
      request<any>('/household/settings/'),
    updateSettings: (data: { min_rating?: number; search_radius_km?: number }) =>
      request<any>('/household/settings/', {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    blockStudent: (studentId: number) =>
      request<any>('/household/block/', {
        method: 'POST',
        body: JSON.stringify({ student_id: studentId }),
      }),
    unblockStudent: (studentId: number) =>
      request<any>('/household/block/', {
        method: 'DELETE',
        body: JSON.stringify({ student_id: studentId }),
      }),
  },

  payments: {
    initiateEscrow: (taskId: number, phoneNumber: string) =>
      request<any>('/payments/initiate-escrow/', {
        method: 'POST',
        body: JSON.stringify({ task_id: taskId, phone_number: phoneNumber }),
      }),
    releaseEscrow: (taskId: number) =>
      request<any>('/payments/release-escrow/', {
        method: 'POST',
        body: JSON.stringify({ task_id: taskId }),
      }),
    checkStatus: (checkoutRequestId: string) =>
      request<any>('/payments/check-status/', {
        method: 'POST',
        body: JSON.stringify({ checkout_request_id: checkoutRequestId }),
      }),
  },

  ratings: {
    create: (taskId: number, ratedUserId: number, score: number, comment: string) =>
      request<any>('/ratings/', {
        method: 'POST',
        body: JSON.stringify({
          task: taskId,
          rated_user: ratedUserId,
          score,
          comment,
        }),
      }),
    getUserSummary: (userId: number) => request<any>(`/ratings/summary/${userId}/`),
  },

  notifications: {
    list: () => request<{ notifications: any[]; unread_count: number }>('/notifications/'),
    markAllRead: () => request<any>('/notifications/', { method: 'PATCH' }),
  },

  cancellationPolicy: {
    get: () => request<any>('/cancellation-policy/'),
    update: (payload: { free_before_hours?: number; partial_refund_pct?: number }) =>
      request<any>('/cancellation-policy/', {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }),
  },

  // --- Geolocation: consent, address search, location policy ---
  geo: {
    /** Location-collection notice status for the signed-in student. */
    getConsent: () => request<GeoConsentInfo>('/geo/consent/'),
    /** Record consent (timestamp + version kept server-side). */
    acceptConsent: (version: string) =>
      request<{ consented: boolean; version: string }>('/geo/consent/', {
        method: 'POST',
        body: JSON.stringify({ version }),
      }),
    /** Address search (OpenStreetMap Nominatim, Kenya-scoped, no API key). */
    searchPlaces: (q: string) =>
      request<{ results: PlaceResult[]; error?: string }>(
        `/geo/places/?q=${encodeURIComponent(q)}`,
      ),
    /** Reverse geocode coordinates to an address label. */
    reverseGeocode: (lat: number, lng: number) =>
      request<{ results: PlaceResult[]; error?: string }>(
        `/geo/places/?lat=${lat}&lng=${lng}`,
      ),
    /** Location verification policy (retention, thresholds). */
    getPolicy: () =>
      request<{
        retention_days: number;
        low_accuracy_threshold_m: number;
        allow_flagged_when_denied: boolean;
        max_time_skew_seconds: number;
        max_speed_mps: number;
      }>('/location-policy/'),
    updatePolicy: (payload: Record<string, number | boolean>) =>
      request<any>('/location-policy/', {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }),
  },
};
