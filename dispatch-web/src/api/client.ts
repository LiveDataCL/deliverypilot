import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'

const ACCESS_TOKEN_KEY = 'dp_access_token'
const REFRESH_TOKEN_KEY = 'dp_refresh_token'

export const tokenStorage = {
  getAccess: () => localStorage.getItem(ACCESS_TOKEN_KEY),
  getRefresh: () => localStorage.getItem(REFRESH_TOKEN_KEY),
  set: (accessToken: string, refreshToken: string) => {
    localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
  },
  clear: () => {
    localStorage.removeItem(ACCESS_TOKEN_KEY)
    localStorage.removeItem(REFRESH_TOKEN_KEY)
  },
}

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? 'http://localhost:8000',
})

apiClient.interceptors.request.use((config) => {
  const token = tokenStorage.getAccess()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Single-flight refresh: concurrent 401s while a refresh is already in-flight
// wait on the same promise instead of each firing their own /auth/refresh call.
let refreshPromise: Promise<string> | null = null

async function refreshAccessToken(): Promise<string> {
  const refreshToken = tokenStorage.getRefresh()
  if (!refreshToken) {
    throw new Error('no_refresh_token')
  }
  const response = await axios.post(
    `${apiClient.defaults.baseURL}/api/v1/auth/refresh`,
    { refresh_token: refreshToken },
  )
  const { access_token, refresh_token } = response.data
  tokenStorage.set(access_token, refresh_token)
  return access_token
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined

    if (error.response?.status !== 401 || !originalRequest || originalRequest._retried) {
      throw error
    }

    originalRequest._retried = true
    try {
      refreshPromise ??= refreshAccessToken()
      const newAccessToken = await refreshPromise
      originalRequest.headers.Authorization = `Bearer ${newAccessToken}`
      return apiClient(originalRequest)
    } catch (refreshError) {
      tokenStorage.clear()
      throw refreshError
    } finally {
      refreshPromise = null
    }
  },
)
