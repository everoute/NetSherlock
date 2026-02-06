import { createContext, useContext, useState, ReactNode } from 'react'

interface AuthContextType {
  isAuthenticated: boolean
  username: string | null
  isLoading: boolean
  login: (username: string, password: string) => boolean
  logout: () => void
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

// Initialize auth state from localStorage
function getInitialAuthState() {
  const storedUsername = localStorage.getItem('username')
  return {
    isAuthenticated: !!storedUsername,
    username: storedUsername,
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const initial = getInitialAuthState()
  const [isAuthenticated, setIsAuthenticated] = useState(initial.isAuthenticated)
  const [username, setUsername] = useState<string | null>(initial.username)

  const login = (username: string, password: string): boolean => {
    // Simple validation: username and password must both be 'admin'
    if (username === 'admin' && password === 'admin') {
      setUsername(username)
      setIsAuthenticated(true)
      localStorage.setItem('username', username)
      return true
    }
    return false
  }

  const logout = () => {
    setUsername(null)
    setIsAuthenticated(false)
    localStorage.removeItem('username')
  }

  return (
    <AuthContext.Provider value={{ isAuthenticated, username, isLoading: false, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
