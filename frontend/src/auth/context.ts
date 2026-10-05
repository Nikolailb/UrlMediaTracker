import { createContext, useContext } from 'react'

export type Session = { id: string; username: string; is_admin: boolean; safe_view_enabled: boolean; csrf_token: string }
export type User = { id: string; username: string }
export type AuthContextValue = {
  session: Session | null | undefined
  selectedUser: string
  users: User[]
  login: (username: string, password: string) => Promise<void>
  acceptInvite: (token: string, username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  setSafeView: (enabled: boolean) => Promise<void>
  selectUser: (id: string) => void
  createInvite: () => Promise<string>
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('AuthProvider missing')
  return value
}
