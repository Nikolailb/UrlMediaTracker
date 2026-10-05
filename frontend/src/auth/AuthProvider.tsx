import { useEffect, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { get, post, setApiContext } from '@/api/client'

import { AuthContext, type Session, type User } from './context'

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const [session, setSession] = useState<Session | null | undefined>(undefined)
  const [selectedUser, setSelectedUser] = useState('')
  const [users, setUsers] = useState<User[]>([])

  function install(next: Session | null) {
    setSession(next)
    setSelectedUser('')
    setApiContext(next?.csrf_token ?? '')
    qc.clear()
  }

  useEffect(() => {
    get<Session>('/auth/me').then((value) => {
      install(value)
    }).catch(() => install(null))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (session?.is_admin) get<User[]>('/auth/users').then(setUsers).catch(() => setUsers([]))
  }, [session?.is_admin])

  async function login(username: string, password: string) {
    install(await post<Session>('/auth/login', { username, password }))
  }
  async function acceptInvite(token: string, username: string, password: string) {
    install(await post<Session>('/auth/accept-invite', { token, username, password }))
  }
  async function logout() {
    await post('/auth/logout')
    install(null)
  }
  async function setSafeView(enabled: boolean) {
    await post(`/auth/safe-view?enabled=${enabled}`)
    setSession((s) => s ? { ...s, safe_view_enabled: enabled } : s)
    qc.clear()
  }
  function selectUser(id: string) {
    setSelectedUser(id)
    setApiContext(session?.csrf_token ?? '', id)
    qc.clear()
  }
  async function createInvite() {
    const value = await post<{ token: string }>('/auth/invites')
    return `${window.location.origin}/?invite=${encodeURIComponent(value.token)}`
  }
  return <AuthContext.Provider value={{ session, selectedUser, users, login, acceptInvite, logout, setSafeView, selectUser, createInvite }}>{children}</AuthContext.Provider>
}
