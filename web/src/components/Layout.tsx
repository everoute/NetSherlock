import { Outlet } from 'react-router'
import { Header } from './Header'
import { Sidebar } from './Sidebar'

export function Layout() {
  return (
    <div className="h-screen flex flex-col">
      <Header />
      <div className="flex-1 flex overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto bg-white">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
