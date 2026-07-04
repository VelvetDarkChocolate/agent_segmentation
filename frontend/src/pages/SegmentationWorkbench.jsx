import { useEffect, useState } from 'react'
import { api } from '../services/api'

export default function SegmentationWorkbench({ onOpenAssistant }) {
  const [cases, setCases] = useState([])
  const [caseId, setCaseId] = useState('')
  const [threshold, setThreshold] = useState(0.5)
  const [task, setTask] = useState(null)
  const [result, setResult] = useState(null)
  const [realResults, setRealResults] = useState([])
  const [activeIndex, setActiveIndex] = useState(0)
  const [files, setFiles] = useState([])
  const [running, setRunning] = useState(false)
  const [queueRunning, setQueueRunning] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get('/api/cases').then((response) => {
      setCases(response.data)
      if (response.data[0]) setCaseId(response.data[0].case_id)
    }).catch(() => setError('病例接口未连接'))
  }, [])

  useEffect(() => {
    if (!task?.task_id || task.state === 'SUCCESS' || task.state === 'FAILURE') return undefined

    const timer = setInterval(async () => {
      const response = await api.get(`/api/tasks/${task.task_id}`)
      setTask(response.data)
      if (response.data.state === 'SUCCESS') {
        setResult(response.data.result)
        setRealResults(response.data.result?.results || [])
        localStorage.setItem('latestSegmentationResult', JSON.stringify(response.data.result || {}))
        clearInterval(timer)
      }
    }, 1000)

    return () => clearInterval(timer)
  }, [task?.task_id, task?.state])

  async function startSegmentation() {
    if (!files.length) {
      setError('请先选择要分割的 CT/MRI 切片图片')
      return
    }

    setError('')
    setTask(null)
    setResult(null)
    setRealResults([])
    setActiveIndex(0)
    setRunning(true)

    const formData = new FormData()
    files.forEach((file) => formData.append('files', file))
    formData.append('alpha', String(threshold))
    formData.append('model_preset', 'abdomen')
    formData.append('inference_mode', 'accurate')

    try {
      const response = await api.post('/predict/sync', formData, {
        timeout: 120000,
        headers: { 'Content-Type': 'multipart/form-data' },
      })

      if (response.data.status !== 'success') {
        throw new Error(response.data.message || '分割失败')
      }

      const nextResult = {
        ...response.data,
        model_name: 'MMRSG-UNet epoch_241.pth',
        created_at: new Date().toISOString(),
      }
      setRealResults(nextResult.results || [])
      localStorage.setItem('latestSegmentationResult', JSON.stringify(nextResult))
    } catch (err) {
      setError(err.response?.data?.message || err.message || '真实模型推理失败')
    } finally {
      setRunning(false)
    }
  }

  async function startQueuedSegmentation() {
    if (!caseId) {
      setError('请先在病例管理中上传病例，并选择要分割的病例')
      return
    }

    setError('')
    setResult(null)
    setRealResults([])
    setActiveIndex(0)
    setQueueRunning(true)
    try {
      const response = await api.post('/api/v1/segmentations', {
        case_id: caseId,
        model_name: 'Seg-Model v2.0',
        threshold: Number(threshold),
      })
      setTask(response.data)
    } catch (err) {
      setError(err.response?.data?.detail || '任务提交失败')
    } finally {
      setQueueRunning(false)
    }
  }

  const activeResult = realResults[activeIndex]

  return (
    <section className="page">
      <div className="page-title">
        <span className="step">2</span>
        <div>
          <h2>医学图像分割工作台</h2>
          <p>AI 自动分割 + 阈值调节 + 人工修正入口</p>
        </div>
      </div>

      <div className="workbench">
        <div className="viewer card">
          <div className={activeResult ? 'real-result-viewer' : result ? 'fake-ct segmented' : 'fake-ct'}>
            <div className="viewer-toolbar">
              <span>{activeResult ? `文件: ${activeResult.filename}` : result ? '分割结果预览' : '原始影像预览'}</span>
              <span>{activeResult ? 'MMRSG-UNet Processing' : result?.preview ? `${result.preview.slice_index} / ${result.preview.total_slices}` : '128 / 256'}</span>
            </div>
            {activeResult ? (
              <img src={activeResult.image_base64 || activeResult.overlay_url} alt={`${activeResult.filename} segmentation`} />
            ) : (
              <>
                <div className="organ liver"></div>
                <div className="organ tumor"></div>
                <div className="organ spleen"></div>
                <div className="cross-line horizontal"></div>
                <div className="cross-line vertical"></div>
              </>
            )}
            {!activeResult && result && (
              <div className="segmentation-labels">
                <span className="label-red">肝脏 1423.6 cm³</span>
                <span className="label-green">肿瘤 38.7 cm³</span>
                <span className="label-blue">脾脏 96.4 cm³</span>
              </div>
            )}
          </div>
          <div className="thumbnail-row">
            {realResults.length ? (
              realResults.map((item, index) => (
                <button
                  key={item.filename}
                  type="button"
                  className={index === activeIndex ? 'thumb active' : 'thumb'}
                  onClick={() => setActiveIndex(index)}
                >
                  {index + 1}
                </button>
              ))
            ) : (
              Array.from({ length: 8 }).map((_, index) => (
                <div key={index} className={index === 4 ? 'thumb active' : 'thumb'}>
                  {124 + index}
                </div>
              ))
            )}
          </div>
        </div>

        <div className="panel card">
          <label>病例选择</label>
          <select value={caseId} onChange={(event) => setCaseId(event.target.value)}>
            <option value="">请选择病例</option>
            {cases.map((item) => (
              <option key={item.case_id} value={item.case_id}>{item.case_id}</option>
            ))}
          </select>

          <label>待分割切片</label>
          <input
            type="file"
            multiple
            accept="image/*"
            onChange={(event) => {
              setFiles(Array.from(event.target.files || []))
              setRealResults([])
              setResult(null)
              setError('')
            }}
          />
          <small className="hint">{files.length ? `已选择 ${files.length} 张图片` : '请选择 PNG/JPG 切片，使用 epoch_241.pth 真模型推理'}</small>

          <label>模型选择</label>
          <select defaultValue="Seg-Model v2.0">
            <option>Seg-Model v2.0</option>
            <option>Seg-Model v1.2</option>
          </select>

          <label>阈值 Threshold: {threshold}</label>
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={threshold}
            onChange={(event) => setThreshold(event.target.value)}
          />

          <button type="button" onClick={startSegmentation} disabled={running}>
            {running ? '同步推理中...' : '小图同步分割'}
          </button>
          <button type="button" className="secondary-action" onClick={startQueuedSegmentation} disabled={queueRunning || running}>
            {queueRunning ? '任务提交中...' : '提交病例任务'}
          </button>
          {error && <p className="hint error">{error}</p>}

          {task && (
            <div className="progress-box">
              <p>{task.message || '任务已提交'}</p>
              <div className="progress">
                <div style={{ width: `${task.progress || 0}%` }}></div>
              </div>
              <small>Task ID: {task.task_id}</small>
            </div>
          )}

          {activeResult && (
            <div className="metrics">
              <h3>真实模型输出</h3>
              <div className="organ-list">
                {(activeResult.metrics || []).length ? (
                  activeResult.metrics.map((metric) => (
                    <span key={metric.organ}>
                      {metric.organ}: {metric.percentage}
                    </span>
                  ))
                ) : (
                  <span>未检测到显著器官区域</span>
                )}
              </div>
              <button
                type="button"
                className="secondary-action"
                onClick={() => {
                  onOpenAssistant?.()
                }}
              >
                用 DeepSeek 助手分析
              </button>
            </div>
          )}

          {!activeResult && result && (
            <div className="metrics">
              <h3>评估指标</h3>
              <p>Dice: {result.metrics.dice}</p>
              <p>IoU: {result.metrics.iou}</p>
              <p>推理耗时: {result.metrics.latency_seconds}s</p>
              <h3>分割结果</h3>
              <div className="organ-list">
                {result.organs.map((organ) => (
                  <span key={organ.name}>
                    {organ.name}: {organ.volume_cm3} cm³
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
