import { Plus } from 'lucide-react'
import { Link } from 'react-router'
import logo from '@/assets/logo.svg'

export function Header() {
  return (
    <header className="bg-white border-b border-gray-200 px-6 py-4">
      <div className="flex items-center justify-between">
        <Link
          to="/"
          className="flex items-center gap-2 hover:opacity-80 transition-opacity cursor-pointer"
          title="Go to home page"
        >
          <img src={logo} alt="NetSherlock Logo" className="h-8 w-8" />
          <span className="text-2xl font-bold text-gray-900">NETSHERLOCK</span>
        </Link>
        <Link
          to="/tasks/new"
          className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Plus className="h-4 w-4" />
          New Task
        </Link>
      </div>
    </header>
  )
}
