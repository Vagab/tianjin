import { useState } from 'react'
import { api } from '../api/client'

interface Props {
  onAuth: () => void
}

export function Auth({ onAuth }: Props) {
  const [mode, setMode] = useState<'login' | 'signup'>('login')
  const [key, setKey] = useState('')
  const [newKey, setNewKey] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await api.login(key)
      onAuth()
    } catch (err: any) {
      setError(err.message || 'Invalid key')
    } finally {
      setLoading(false)
    }
  }

  const handleSignup = async () => {
    setError('')
    setLoading(true)
    try {
      const res = await api.signup()
      setNewKey(res.key!)
    } catch (err: any) {
      setError(err.message || 'Signup failed')
    } finally {
      setLoading(false)
    }
  }

  const handleContinue = () => {
    setNewKey(null)
    onAuth()
  }

  // Show the new key after signup
  if (newKey) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="w-full max-w-sm">
          <div className="rounded-xl bg-surface-raised border border-border p-6 space-y-5">
            <div>
              <h1 className="text-lg font-semibold tracking-tight mb-1">Your Account Key</h1>
              <p className="text-xs text-text-muted">
                Save this key. It's the only way to access your account. There is no recovery.
              </p>
            </div>

            <div className="bg-surface-overlay border border-accent/30 rounded-lg p-4 text-center">
              <code className="text-xl font-mono tracking-widest text-accent select-all">
                {newKey.replace(/(\d{4})/g, '$1 ').trim()}
              </code>
            </div>

            <button
              onClick={() => navigator.clipboard.writeText(newKey)}
              className="w-full px-4 py-2 rounded-lg text-sm font-medium
                bg-surface-overlay text-text-secondary border border-border
                hover:bg-surface-overlay/80 transition-colors"
            >
              Copy to Clipboard
            </button>

            <button
              onClick={handleContinue}
              className="w-full px-4 py-2.5 rounded-lg text-sm font-medium
                bg-accent text-white hover:bg-accent-hover transition-colors"
            >
              I've Saved My Key
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="rounded-xl bg-surface-raised border border-border p-6 space-y-5">
          <div className="text-center">
            <h1 className="text-lg font-semibold tracking-tight">Poly</h1>
            <p className="text-xs text-text-muted mt-1">Polymarket BTC Bot</p>
          </div>

          {mode === 'login' ? (
            <form onSubmit={handleLogin} className="space-y-4">
              <div>
                <label className="block text-xs text-text-muted mb-1.5">Account Key</label>
                <input
                  type="text"
                  value={key}
                  onChange={(e) => setKey(e.target.value)}
                  placeholder="0000 0000 0000 0000"
                  className="w-full px-3 py-2.5 rounded-lg text-sm font-mono
                    bg-surface-overlay border border-border text-text-primary
                    placeholder:text-text-muted/50
                    focus:outline-none focus:border-accent/50 focus:ring-1 focus:ring-accent/30
                    tracking-widest text-center"
                  maxLength={19}
                  autoFocus
                />
              </div>

              {error && (
                <p className="text-xs text-red text-center">{error}</p>
              )}

              <button
                type="submit"
                disabled={loading || key.replace(/\s/g, '').length < 16}
                className="w-full px-4 py-2.5 rounded-lg text-sm font-medium
                  bg-accent text-white hover:bg-accent-hover transition-colors
                  disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {loading ? 'Signing in...' : 'Sign In'}
              </button>

              <button
                type="button"
                onClick={() => { setMode('signup'); setError('') }}
                className="w-full text-xs text-text-muted hover:text-text-secondary transition-colors"
              >
                Don't have a key? Create account
              </button>
            </form>
          ) : (
            <div className="space-y-4">
              <p className="text-sm text-text-secondary text-center">
                Generate a 16-digit account key. No email needed.
              </p>

              {error && (
                <p className="text-xs text-red text-center">{error}</p>
              )}

              <button
                onClick={handleSignup}
                disabled={loading}
                className="w-full px-4 py-2.5 rounded-lg text-sm font-medium
                  bg-accent text-white hover:bg-accent-hover transition-colors
                  disabled:opacity-40"
              >
                {loading ? 'Creating...' : 'Generate Key'}
              </button>

              <button
                type="button"
                onClick={() => { setMode('login'); setError('') }}
                className="w-full text-xs text-text-muted hover:text-text-secondary transition-colors"
              >
                Already have a key? Sign in
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
