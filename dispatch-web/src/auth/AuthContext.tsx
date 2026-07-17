import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { apiClient, tokenStorage } from '../api/client'

interface CurrentUser {
  id: number
  business_id: number
  role: string
  email: string
  phone: string | null
  is_active: boolean
}

interface AuthContextValue {
  user: CurrentUser | null
  isLoading: boolean
  login: (email: string, password: string) => Promise<void>
  loginWithTokens: (accessToken: string, refreshToken: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const fetchMe = useCallback(async () => {
    if (!tokenStorage.getAccess()) {
      setUser(null)
      setIsLoading(false)
      return
    }
    try {
      const response = await apiClient.get<CurrentUser>('/api/v1/auth/me')
      setUser(response.data)
    } catch {
      tokenStorage.clear()
      setUser(null)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchMe()
  }, [fetchMe])

  const login = useCallback(async (email: string, password: string) => {
    const response = await apiClient.post('/api/v1/auth/login', { email, password })
    tokenStorage.set(response.data.access_token, response.data.refresh_token)
    await fetchMe()
  }, [fetchMe])

  // For flows that already have a token pair from the API response itself
  // (accept-invite returns tokens directly, same as login does) -- no
  // second round-trip needed, just store and refetch /me.
  const loginWithTokens = useCallback(
    async (accessToken: string, refreshToken: string) => {
      tokenStorage.set(accessToken, refreshToken)
      await fetchMe()
    },
    [fetchMe],
  )

  const logout = useCallback(() => {
    tokenStorage.clear()
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, isLoading, login, loginWithTokens, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return ctx
}
