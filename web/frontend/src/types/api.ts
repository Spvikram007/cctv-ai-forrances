export interface StandardResponse<T> {
  success: boolean;
  data: T | null;
  error: ErrorDetail | null;
  correlation_id: string;
  timestamp: string;
}

export interface ErrorDetail {
  code: string;
  message: string;
  details?: unknown;
}

export interface PaginationQuery {
  limit?: number;
  offset?: number;
  search?: string;
  online_only?: boolean;
}
