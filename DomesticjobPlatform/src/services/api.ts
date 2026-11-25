import { Platform } from 'react-native';

// Android emulator uses 10.0.2.2 to reach host localhost.
// Real Android/iOS devices on LAN need the PC's actual WiFi IP.
// Update LAN_IP if your PC's IP changes (check with ipconfig).
const LAN_IP = '10.55.61.116';

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
    }) =>
      request<any>('/tasks/', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    submitBid: (taskId: number, amount: number | string, message: string) =>
      request<any>(`/tasks/${taskId}/bids/`, {
        method: 'POST',
        body: JSON.stringify({ amount, message }),
      }),
    acceptBid: (taskId: number, bidId: number) =>
      request<any>(`/tasks/${taskId}/accept-bid/`, {
        method: 'POST',
        body: JSON.stringify({ bid_id: bidId }),
      }),
    markComplete: (taskId: number) =>
      request<any>(`/tasks/${taskId}/complete/`, {
        method: 'POST',
      }),
    dispute: (taskId: number) =>
      request<any>(`/tasks/${taskId}/dispute/`, {
        method: 'POST',
      }),
    getMessages: (taskId: number) => request<any[]>(`/tasks/${taskId}/messages/`),
    sendMessage: (taskId: number, content: string, receiverId?: number) =>
      request<any>(`/tasks/${taskId}/messages/`, {
        method: 'POST',
        body: JSON.stringify({ content, receiver_id: receiverId }),
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
};
