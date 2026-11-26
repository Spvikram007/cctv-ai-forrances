/**
 * Authenticated Real-Time WebSocket Gateway Client.
 *
 * Security Design:
 *   1. Primary authentication via secure HttpOnly session cookie ('cctv_session').
 *      Zero long-lived tokens exposed in URL query strings or browser history.
 *   2. Optional fallback to single-use ticket (?ticket=...) via POST /api/v1/auth/ws-ticket.
 *   3. Bounded exponential backoff reconnection (1s to 30s).
 *   4. Clean teardown on unmount and session revocation.
 */

import { authApi } from './auth';

export interface WebSocketEventMessage {
  topic: string;
  data: unknown;
  timestamp: string;
  source: string;
}

export type WebSocketEventHandler = (event: WebSocketEventMessage) => void;

export class SurveillanceWebSocketClient {
  private ws: WebSocket | null = null;
  private handlers: Set<WebSocketEventHandler> = new Set();
  private reconnectTimeout: NodeJS.Timeout | null = null;
  private backoffMs: number = 1000;
  private maxBackoffMs: number = 30000;
  private isConnecting: boolean = false;
  private isConnected: boolean = false;
  private shouldReconnect: boolean = true;
  private useTicketFallback: boolean = false;

  async connect(preferTicket: boolean = false) {
    if (this.isConnected || this.isConnecting) return;

    this.shouldReconnect = true;
    this.useTicketFallback = preferTicket;
    await this.initSocket();
  }

  private async initSocket() {
    if (!this.shouldReconnect) return;
    this.isConnecting = true;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    let url = `${protocol}//${host}/api/v1/ws/events`;

    // If ticket fallback is requested (e.g. cross-origin or cookie-restricted contexts)
    if (this.useTicketFallback) {
      try {
        const ticketRes = await authApi.getWebSocketTicket();
        if (ticketRes?.ticket) {
          url += `?ticket=${encodeURIComponent(ticketRes.ticket)}`;
        }
      } catch {
        // Fall back to direct cookie handshake
      }
    }

    try {
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        this.isConnected = true;
        this.isConnecting = false;
        this.backoffMs = 1000; // Reset backoff on successful connect
      };

      this.ws.onmessage = (messageEvent) => {
        try {
          const payload = JSON.parse(messageEvent.data);
          if (payload && payload.topic) {
            this.handlers.forEach((handler) => {
              try {
                handler(payload as WebSocketEventMessage);
              } catch {
                // Ignore subscriber errors
              }
            });
          }
        } catch {
          // Ignore non-JSON control messages (pong, etc.)
        }
      };

      this.ws.onclose = (event) => {
        this.isConnected = false;
        this.isConnecting = false;

        // If closed with policy violation (4401), switch to ticket fallback on next retry
        if (event.code === 4401 || event.code === 1008) {
          this.useTicketFallback = true;
        }

        if (this.shouldReconnect) {
          this.scheduleReconnect();
        }
      };

      this.ws.onerror = () => {
        if (this.ws) {
          this.ws.close();
        }
      };
    } catch {
      this.isConnected = false;
      this.isConnecting = false;
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect() {
    if (this.reconnectTimeout) clearTimeout(this.reconnectTimeout);
    this.reconnectTimeout = setTimeout(async () => {
      this.backoffMs = Math.min(this.backoffMs * 1.5, this.maxBackoffMs);
      await this.initSocket();
    }, this.backoffMs);
  }

  subscribe(handler: WebSocketEventHandler): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  disconnect() {
    this.shouldReconnect = false;
    this.isConnected = false;
    this.isConnecting = false;

    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.handlers.clear();
  }
}

export const wsClient = new SurveillanceWebSocketClient();
