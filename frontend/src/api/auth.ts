/**
 * Auth client — login/logout for the pilgrim UI.
 *
 * Token'ı ``localStorage``'da tutar (PilgrimUI token key: ``pilgrim_token``),
 * ``request`` helper'ın her isteğine Bearer ekler; 401'de token'ı siler ve
 * /login route'una yönlendirir (router guard'ı tekrar login gösterir).
 */

const API_BASE = '/api/v1';
export const TOKEN_KEY = 'pilgrim_token';

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* private mode: token bu oturumda kalır */
  }
}

export function clearToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* noop */
  }
}

export async function login(username: string, password: string): Promise<void> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail || `Login failed: ${res.status}`);
  }
  const data = (await res.json()) as { token: string };
  setToken(data.token);
}

export async function verifyToken(): Promise<boolean> {
  const token = getToken();
  if (!token) return false;
  try {
    const res = await fetch(`${API_BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) return true;
  } catch {
    /* network error → not verified */
  }
  clearToken();
  return false;
}

export function logout(): void {
  clearToken();
}
