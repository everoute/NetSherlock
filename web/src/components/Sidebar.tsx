import { Link, useLocation } from 'react-router'
import { FileText, ListTodo } from 'lucide-react'
import { cn } from '@/lib/utils'

const navigation = [
  { name: 'Tasks', href: '/tasks', icon: ListTodo },
  { name: 'Reports', href: '/reports', icon: FileText },
]

export function Sidebar() {
  const location = useLocation()

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
    </div>
  )
}
