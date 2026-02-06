import { Link, useLocation, useNavigate } from 'react-router'
import { FileText, ListTodo, LogOut, Wifi, WifiOff, AlertCircle, User } from 'lucide-react'
import { useAuth } from '@/lib/auth'
import { useBackendStatus } from '@/lib/useBackendStatus'
import { cn } from '@/lib/utils'

const navigation = [
  { name: 'Tasks', href: '/tasks', icon: ListTodo },
  { name: 'Reports', href: '/reports', icon: FileText },
]

export function Sidebar() {
  const location = useLocation()
  const navigate = useNavigate()
  const { username, logout } = useAuth()
  const backendStatus = useBackendStatus()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const getStatusColor = () => {
    switch (backendStatus.status) {
      case 'healthy':
        return 'text-green-600 bg-green-50'
      case 'degraded':
        return 'text-yellow-600 bg-yellow-50'
      case 'offline':
        return 'text-red-600 bg-red-50'
    }
  }

  const getStatusIcon = () => {
    switch (backendStatus.status) {
      case 'healthy':
        return <Wifi className="h-4 w-4" />
      case 'degraded':
        return <AlertCircle className="h-4 w-4" />
      case 'offline':
        return <WifiOff className="h-4 w-4" />
    }
  }

  const getStatusLabel = () => {
    switch (backendStatus.status) {
      case 'healthy':
        return 'Backend Online'
      case 'degraded':
        return 'Backend Degraded'
      case 'offline':
        return 'Backend Offline'
    }
  }

  return (
    <div className="w-64 bg-gray-50 border-r border-gray-200 flex flex-col">
      <nav className="flex-1 px-4 py-6 space-y-1">
        {navigation.map((item) => {
          const isActive = location.pathname.startsWith(item.href)
          return (
            <Link
              key={item.name}
              to={item.href}
              className={cn(
                'flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-lg transition-colors',
                isActive
                  ? 'bg-blue-50 text-blue-700'
                  : 'text-gray-700 hover:bg-gray-100',
              )}
            >
              <item.icon className="h-5 w-5" />
              {item.name}
            </Link>
          )
        })}
      </nav>

      {/* Bottom Section - Aligned to Bottom */}
      <div className="px-4 py-3 border-t border-gray-200 space-y-2 mt-auto">
        {/* Backend Status */}
        <div
          className={cn(
            'flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium',
            getStatusColor(),
          )}
          title={
            backendStatus.error
              ? `${getStatusLabel()}: ${backendStatus.error}`
              : `${getStatusLabel()} | Queue: ${backendStatus.queueSize || 0}`
          }
        >
          {getStatusIcon()}
          <span className="truncate">{getStatusLabel()}</span>
        </div>

        {/* User Info Card */}
        <div className="bg-white rounded-lg border border-gray-200 p-3 shadow-sm hover:shadow-md transition-shadow">
          <div className="flex items-center gap-2.5 mb-2">
            <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center flex-shrink-0">
              <User className="h-4 w-4 text-white" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-gray-900 truncate">@{username}</p>
            </div>
          </div>

          {/* Logout Button */}
          <button
            onClick={handleLogout}
            className="w-full flex items-center justify-center gap-2 px-2.5 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 rounded-md transition-colors border border-transparent hover:border-red-200"
            title="Logout from your account"
          >
            <LogOut className="h-3.5 w-3.5" />
            Logout
          </button>
        </div>
      </div>
    </div>
  )
}
