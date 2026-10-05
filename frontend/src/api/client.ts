/** Base URL — Vite proxies /api → http://localhost:8000 in dev */
const BASE = '/api'
let csrfToken = ''
let libraryUser = ''

export function setApiContext(csrf: string, userId = '') {
  csrfToken = csrf
  libraryUser = userId
}

function headers(json = false): HeadersInit {
  return {
    ...(json ? { 'Content-Type': 'application/json' } : {}),
    ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
    ...(libraryUser ? { 'X-Library-User': libraryUser } : {}),
  }
}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
    this.name = 'ApiError'
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = `HTTP ${res.status}`
    try {
      const body = await res.json()
      message = body?.detail ?? message
      if (typeof message !== 'string') message = JSON.stringify(message)
    } catch {
      // ignore json parse error
    }
    throw new ApiError(res.status, message)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { headers: headers() })
  return handleResponse<T>(res)
}

export async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: headers(true),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  return handleResponse<T>(res)
}

export async function patch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PATCH',
    headers: headers(true),
    body: JSON.stringify(body),
  })
  return handleResponse<T>(res)
}

export async function del(path: string): Promise<void> {
  const res = await fetch(`${BASE}${path}`, { method: 'DELETE', headers: headers() })
  return handleResponse<void>(res)
}

export async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PUT',
    headers: headers(true),
    body: JSON.stringify(body),
  })
  return handleResponse<T>(res)
}

export async function postFile<T>(path: string, file: File): Promise<T> {
  const body = new FormData()
  body.append('file', file)
  const res = await fetch(`${BASE}${path}`, { method: 'POST', headers: headers(), body })
  return handleResponse<T>(res)
}

export async function postBlob(path: string, body: unknown): Promise<Blob> {
  const res = await fetch(`${BASE}${path}`, { method: 'POST', headers: headers(true), body: JSON.stringify(body) })
  if (!res.ok) return handleResponse<Blob>(res)
  return res.blob()
}
