import { StandardResponse, ErrorDetail } from '../types/api';

export class ApiError extends Error {
  code: string;
  status: number;
  details?: unknown;

  constructor(status: number, error: ErrorDetail) {
    super(error.message);
    this.name = 'ApiError';
    this.status = status;
    this.code = error.code;
    this.details = error.details;
  }
}

interface RequestOptions extends RequestInit {
  params?: Record<string, string | number | boolean | undefined>;
}

type UnauthorizedHandler = () => void;

class ApiClient {
  private baseUrl: string = '/api/v1';
  private unauthorizedHandlers: Set<UnauthorizedHandler> = new Set();

  public onUnauthorized(handler: UnauthorizedHandler): () => void {
    this.unauthorizedHandlers.add(handler);
    return () => this.unauthorizedHandlers.delete(handler);
  }

  private notifyUnauthorized() {
    this.unauthorizedHandlers.forEach((handler) => {
      try {
        handler();
      } catch {
        // Ignore handler errors
      }
    });
  }

  private buildUrl(endpoint: string, params?: Record<string, string | number | boolean | undefined>): string {
    const url = new URL(this.baseUrl + (endpoint.startsWith('/') ? endpoint : `/${endpoint}`), window.location.origin);
    if (params) {
      Object.entries(params).forEach(([key, val]) => {
        if (val !== undefined && val !== null && val !== '') {
          url.searchParams.append(key, String(val));
        }
      });
    }
    return url.pathname + url.search;
  }

  private getAuthHeader(): Record<string, string> {
    const token = sessionStorage.getItem('cctv_session_token');
    if (token) {
      return { Authorization: `Bearer ${token}` };
    }
    return {};
  }

  async request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    const { params, headers, ...rest } = options;
    const url = this.buildUrl(endpoint, params);

    const mergedHeaders: HeadersInit = {
      'Content-Type': 'application/json',
      ...this.getAuthHeader(),
      ...(headers as Record<string, string>),
    };

    let response: Response;
    try {
      response = await fetch(url, {
        ...rest,
        headers: mergedHeaders,
        credentials: 'include', // Includes HttpOnly session cookie
      });
    } catch {
      throw new ApiError(0, {
        code: 'NETWORK_ERROR',
        message: 'Network unreachable. Please check LAN connection to surveillance gateway.',
      });
    }

    if (response.status === 401) {
      this.notifyUnauthorized();
    }

    const data: StandardResponse<T> = await response.json().catch(() => ({
      success: false,
      data: null,
      error: { code: 'PARSE_ERROR', message: `Server returned HTTP ${response.status}` },
      correlation_id: 'unknown',
      timestamp: new Date().toISOString(),
    }));

    if (!response.ok || !data.success) {
      const err = data.error || { code: 'HTTP_ERROR', message: `Request failed with HTTP ${response.status}` };
      throw new ApiError(response.status, err);
    }

    return data.data as T;
  }

  get<T>(endpoint: string, params?: Record<string, string | number | boolean | undefined>, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'GET', params });
  }

  post<T>(endpoint: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  put<T>(endpoint: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: 'PUT',
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  delete<T>(endpoint: string, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'DELETE' });
  }
}

export const apiClient = new ApiClient();
