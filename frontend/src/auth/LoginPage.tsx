import { useState } from 'react'
import { useAuth } from './context'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

export function LoginPage() {
  const auth = useAuth()
  const invite = new URLSearchParams(window.location.search).get('invite')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError('')
    setPending(true)
    try {
      if (invite) await auth.acceptInvite(invite, username, password)
      else await auth.login(username, password)
      window.history.replaceState(null, '', '/')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not sign in.')
    } finally {
      setPending(false)
    }
  }
  return <main className="min-h-screen flex items-center justify-center p-4">
    <form onSubmit={submit} className="w-full max-w-sm rounded-xl border bg-card p-6 space-y-4">
      <h1 className="text-xl font-semibold">{invite ? 'Create your account' : 'Sign in to Chapter Tracker'}</h1>
      <label className="block text-sm">Username<Input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required /></label>
      <label className="block text-sm">Password<Input type="password" autoComplete={invite ? 'new-password' : 'current-password'} minLength={invite ? 12 : undefined} value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <Button type="submit" disabled={pending} className="w-full">{invite ? 'Create account' : 'Sign in'}</Button>
    </form>
  </main>
}
