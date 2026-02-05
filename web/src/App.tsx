import { BrowserRouter, Routes, Route, Navigate } from 'react-router'
import { Layout } from './components/Layout'
import { TasksPage } from './pages/TasksPage'
import { TaskDetailPage } from './pages/TaskDetailPage'
import { NewTaskPage } from './pages/NewTaskPage'
import { ReportsPage } from './pages/ReportsPage'
import { ReportDetailPage } from './pages/ReportDetailPage'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/tasks" replace />} />
          <Route path="tasks" element={<TasksPage />} />
          <Route path="tasks/new" element={<NewTaskPage />} />
          <Route path="tasks/:id" element={<TaskDetailPage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="reports/:id" element={<ReportDetailPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
