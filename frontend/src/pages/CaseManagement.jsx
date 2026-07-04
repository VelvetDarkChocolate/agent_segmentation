import { useEffect, useState } from 'react'
import { api } from '../services/api'

export default function CaseManagement() {
  const [files, setFiles] = useState([])
  const [cases, setCases] = useState([])
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')

  async function loadCases() {
    const response = await api.get('/api/cases')
    setCases(response.data)
  }

  useEffect(() => {
    loadCases().catch(() => setMessage('病例接口未连接'))
  }, [])

  async function upload() {
    if (!files.length) {
      setMessage('请先选择影像文件')
      return
    }

    const formData = new FormData()
    Array.from(files).forEach((file) => formData.append('files', file))
    formData.append('modality', 'CT')
    formData.append('body_part', '肝脏')

    setLoading(true)
    setMessage('上传中')
    try {
      await api.post('/api/cases/upload', formData)
      await loadCases()
      setFiles([])
      setMessage('上传成功')
    } catch (error) {
      setMessage(error.response?.data?.detail || '上传失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="page">
      <div className="page-title">
        <span className="step">1</span>
        <div>
          <h2>病例管理 / 数据上传</h2>
          <p>支持 DICOM / NIfTI / PNG 批量上传与病例登记</p>
        </div>
      </div>

      <div className="stats">
        <div>今日上传 <strong>{cases.length}</strong></div>
        <div>处理中任务 <strong>{cases.filter((item) => ['queued', 'running'].includes(item.status)).length}</strong></div>
        <div>完成率 <strong>92.6%</strong></div>
        <div>平均耗时 <strong>3.6 min</strong></div>
      </div>

      <div className="card upload-card">
        <div>
          <strong>拖拽式数据接入</strong>
          <p>{files.length ? `已选择 ${files.length} 个文件` : '选择多张影像切片后提交到病例库'}</p>
        </div>
        <input type="file" multiple onChange={(event) => setFiles(Array.from(event.target.files || []))} />
        <button type="button" onClick={upload} disabled={loading}>
          {loading ? '上传中...' : '提交影像到病例库'}
        </button>
      </div>

      {message && <p className="hint">{message}</p>}

      <div className="card">
        <h3>病例列表</h3>
        <table>
          <thead>
            <tr>
              <th>病例ID</th>
              <th>模态</th>
              <th>部位</th>
              <th>文件数</th>
              <th>状态</th>
              <th>创建时间</th>
            </tr>
          </thead>
          <tbody>
            {cases.map((item) => (
              <tr key={item.case_id}>
                <td>{item.case_id}</td>
                <td>{item.modality}</td>
                <td>{item.body_part}</td>
                <td>{item.file_count}</td>
                <td><span className="status">{item.status_label || item.status}</span></td>
                <td>{item.created_at}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
