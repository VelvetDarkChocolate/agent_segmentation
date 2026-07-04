import { useState } from 'react'
import { BrowserRouter, Navigate, NavLink, Route, Routes } from 'react-router-dom'
import DeepSeekAssistant from './components/DeepSeekAssistant.jsx'
import CaseManagement from './pages/CaseManagement.jsx'
import ModelCenter from './pages/ModelCenter.jsx'
import ResearchAgent from './pages/ResearchAgent.jsx'
import ResultReview from './pages/ResultReview.jsx'
import SegmentationWorkbench from './pages/SegmentationWorkbench.jsx'

const navItems = [
  { to: '/cases', label: '病例管理' },
  { to: '/workbench', label: '分割工作台' },
  { to: '/agent', label: '科研 Agent' },
  { to: '/models', label: '模型中心' },
  { to: '/reports', label: '结果报告' },
]

export default function App() {
  const [assistantOpen, setAssistantOpen] = useState(false)

  return (
    <BrowserRouter>
      <div className="app">
        <aside className="sidebar">
          <div className="brand">
            <div className="logo">+</div>
            <div>
              <h2>医学图像分割平台</h2>
              <p>AI 赋能医学影像</p>
            </div>
          </div>

          <nav>
            {navItems.map((item) => (
              <NavLink key={item.to} to={item.to}>
                {item.label}
              </NavLink>
            ))}
          </nav>
        </aside>

        <main className="main">
          <header className="topbar">
            <div>
              <h1>医学图像分割平台</h1>
              <p>智能分割 · 精准量化 · 高效协同 · 安全合规</p>
            </div>
            <button type="button" className="badge assistant-trigger" onClick={() => setAssistantOpen(true)}>
              AI 赋能医学影像 · 打开 DeepSeek 助手
            </button>
          </header>

          <Routes>
            <Route path="/" element={<Navigate to="/cases" replace />} />
            <Route path="/cases" element={<CaseManagement />} />
            <Route path="/workbench" element={<SegmentationWorkbench />} />
            <Route path="/agent" element={<ResearchAgent />} />
            <Route path="/models" element={<ModelCenter />} />
            <Route path="/reports" element={<ResultReview />} />
          </Routes>
        </main>
      </div>
      <DeepSeekAssistant open={assistantOpen} onClose={() => setAssistantOpen(false)} />
    </BrowserRouter>
  )
}
