import { useEffect, useMemo, useRef, useState } from 'react'
import { analyzeSegmentationWithAuthority, api, getAuthorityStatus } from '../services/api'

const starterPrompts = [
  '解释一下 MMRSG-UNet 的分割流程',
  '如何理解 Dice、IoU 和 HD95 指标？',
]

const authorityPrompts = [
  '基于本地权威 PDF 生成科研汇报',
  '解释该切片的单切片局限性',
  '分析哪些器官需要人工复核',
  '解释 pixel_count 与 Dice/HD95 的区别',
]

function getStoredSegmentationResult() {
  try {
    const stored = JSON.parse(localStorage.getItem('latestSegmentationResult') || '{}')
    return stored?.results?.length ? stored : null
  } catch {
    return null
  }
}

function buildSegmentationContext(results) {
  if (!results.length) return ''

  const lines = [
    '当前分割结果来自后端 /predict 接口和 MMRSG-UNet epoch_241.pth 模型。',
    '这些是模型输出的像素级科研辅助指标，不代表临床诊断。',
  ]

  results.forEach((result, index) => {
    lines.push(`\n[切片 ${index + 1}] 文件名：${result.filename}`)
    const metrics = result.metrics || []
    if (!metrics.length) {
      lines.push('- 未检测到显著器官区域')
      return
    }
    metrics.forEach((metric) => {
      lines.push(`- ${metric.organ}: pixel_count=${metric.pixel_count}, percentage=${metric.percentage}`)
    })
  })

  return lines.join('\n')
}

export default function DeepSeekAssistant({ open, onClose }) {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: '你好，我是平台内置 DeepSeek 科研助手。可以帮你解释分割流程、实验指标和报告内容；本助手不提供临床诊断或治疗建议。',
    },
  ])
  const [input, setInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const [segFiles, setSegFiles] = useState([])
  const [segLoading, setSegLoading] = useState(false)
  const [authorityLoading, setAuthorityLoading] = useState(false)
  const [authorityStatus, setAuthorityStatus] = useState(null)
  const [segmentationResult, setSegmentationResult] = useState(() => getStoredSegmentationResult())
  const [segResults, setSegResults] = useState([])
  const [segIndex, setSegIndex] = useState(0)
  const fileRef = useRef(null)

  const activeSegResult = segResults[segIndex]
  const segmentationContext = useMemo(() => buildSegmentationContext(segResults), [segResults])
  const currentSegmentationResult = useMemo(() => {
    if (segmentationResult?.results?.length) return segmentationResult
    if (!segResults.length) return null
    return {
      status: 'success',
      model_name: 'MMRSG-UNet epoch_241.pth',
      results: segResults,
    }
  }, [segmentationResult, segResults])
  const chatHistory = useMemo(
    () => messages.filter((item) => item.role === 'user' || item.role === 'assistant'),
    [messages],
  )

  useEffect(() => {
    if (!open) return
    const stored = getStoredSegmentationResult()
    if (stored?.results?.length) {
      setSegmentationResult(stored)
      setSegResults(stored.results)
      setSegIndex(0)
    }
    getAuthorityStatus()
      .then((response) => setAuthorityStatus(response.data))
      .catch(() => setAuthorityStatus({ store_type: 'unavailable', indexed_chunks: 0, chroma_ready: false }))
  }, [open])

  if (!open) return null

  function appendAssistantMessage(message) {
    setMessages((items) => [...items, { role: 'assistant', ...message }])
  }

  async function sendMessage(text = input) {
    const trimmed = text.trim()
    if (!trimmed || chatLoading) return

    const nextMessages = [...messages, { role: 'user', content: trimmed }]
    setMessages(nextMessages)
    setInput('')
    setChatLoading(true)

    try {
      const response = await api.post('/api/agent/chat', {
        message: trimmed,
        history: chatHistory.slice(-8),
        segmentation_context: segmentationContext,
      })
      setMessages([
        ...nextMessages,
        {
          role: 'assistant',
          content: response.data.answer,
        },
      ])
    } catch (err) {
      setMessages([
        ...nextMessages,
        {
          role: 'assistant',
          content: err.response?.data?.detail || err.message || 'DeepSeek 调用失败，请检查后端 API key 配置。',
        },
      ])
    } finally {
      setChatLoading(false)
    }
  }

  async function runSegmentation() {
    if (!segFiles.length || segLoading) return

    const formData = new FormData()
    segFiles.forEach((file) => formData.append('files', file))
    formData.append('alpha', '0.5')
    formData.append('model_preset', 'abdomen')
    formData.append('inference_mode', 'accurate')

    setSegLoading(true)
    setSegResults([])
    setSegIndex(0)

    try {
      const response = await api.post('/predict', formData, {
        timeout: 120000,
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      if (response.data.status !== 'success') {
        throw new Error(response.data.message || '分割失败')
      }
      const nextSegmentationResult = {
        ...response.data,
        model_name: 'MMRSG-UNet epoch_241.pth',
        created_at: new Date().toISOString(),
      }
      const results = nextSegmentationResult.results || []
      setSegmentationResult(nextSegmentationResult)
      setSegResults(results)
      localStorage.setItem('latestSegmentationResult', JSON.stringify(nextSegmentationResult))
      setMessages((items) => [
        ...items,
        {
          role: 'assistant',
          content: `已完成 ${results.length} 张切片分割。我已经整理好当前分割指标，接下来可以直接点“基于本地权威 PDF 生成科研汇报”，我会调用 ChromaDB 知识向量库并带 PDF citation。`,
        },
      ])
    } catch (err) {
      setMessages((items) => [
        ...items,
        {
          role: 'assistant',
          content: err.response?.data?.message || err.message || '分割失败，请检查模型服务。',
        },
      ])
    } finally {
      setSegLoading(false)
    }
  }

  async function runAuthorityAnalysis(text) {
    if (!currentSegmentationResult?.results?.length || authorityLoading) {
      appendAssistantMessage({
        content: '请先在分割工作台或助手窗口完成一次 /predict 分割，再生成本地权威 PDF 科研分析。',
      })
      return
    }

    const nextMessages = [...messages, { role: 'user', content: text }]
    setMessages(nextMessages)
    setAuthorityLoading(true)

    try {
      const response = await analyzeSegmentationWithAuthority({
        message: text,
        segmentation_result: currentSegmentationResult,
        top_k: 8,
        authority_only: true,
        min_authority_level: 4,
      })
      setMessages([
        ...nextMessages,
        {
          role: 'assistant',
          content: response.data.answer,
          citations: response.data.citations || [],
          toolsUsed: response.data.tools_used || [],
          authorityContext: response.data.authority_context,
          segmentationFacts: response.data.segmentation_facts,
        },
      ])
    } catch (err) {
      setMessages([
        ...nextMessages,
        {
          role: 'assistant',
          content: err.response?.data?.detail || err.message || '本地权威 PDF 科研分析失败，请检查后端服务。',
        },
      ])
    } finally {
      setAuthorityLoading(false)
    }
  }

  return (
    <div className="assistant-overlay" role="dialog" aria-modal="true">
      <div className="assistant-modal">
        <header className="assistant-header">
          <div>
            <h2>DeepSeek 医学影像助手</h2>
            <p>科研辅助 · 指标解释 · 图像分割预览</p>
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="关闭助手">×</button>
        </header>

        <div className="assistant-body">
          <section className="assistant-chat">
            <div className="assistant-messages">
              {messages.map((item, index) => (
                <div key={`${item.role}-${index}`} className={`assistant-message ${item.role}`}>
                  <span>{item.role === 'user' ? '我' : 'AI'}</span>
                  <div className="assistant-message-content">
                    <p>{item.content}</p>
                    {!!item.citations?.length && (
                      <div className="assistant-citations">
                        <strong>PDF citations</strong>
                        {item.citations.map((citation) => (
                          <div className="assistant-citation" key={citation.chunk_id}>
                            <b>[{citation.source_id}] {citation.title}</b>
                            <small>{citation.publisher} · pages {citation.page_start}-{citation.page_end} · {citation.retrieval_backend || 'retrieval'}</small>
                            <a href={citation.source_url} target="_blank" rel="noreferrer">{citation.source_url}</a>
                          </div>
                        ))}
                      </div>
                    )}
                    {!!item.toolsUsed?.length && (
                      <div className="assistant-tool-tags">
                        {item.toolsUsed.map((tool) => <small key={tool}>{tool}</small>)}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {(chatLoading || authorityLoading) && (
                <div className="assistant-message assistant">
                  <span>AI</span>
                  <div className="assistant-message-content">
                    <p>{authorityLoading ? '正在检索 ChromaDB 本地权威 PDF 知识库...' : 'DeepSeek 正在思考...'}</p>
                  </div>
                </div>
              )}
            </div>

            <div className="starter-row">
              {starterPrompts.map((prompt) => (
                <button key={prompt} type="button" onClick={() => sendMessage(prompt)}>
                  {prompt}
                </button>
              ))}
              <button
                type="button"
                disabled={!segmentationContext}
                onClick={() => runAuthorityAnalysis('请基于当前真实分割结果，结合本地权威 PDF 知识库，按科研汇报格式总结模型输出、器官面积占比和注意事项。不要编造 Dice、HD95 或临床诊断。')}
              >
                解读当前分割结果
              </button>
            </div>

            <div className="authority-action-row">
              {authorityPrompts.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  disabled={!currentSegmentationResult?.results?.length || authorityLoading}
                  onClick={() => runAuthorityAnalysis(prompt)}
                >
                  {prompt}
                </button>
              ))}
            </div>

            <form
              className="assistant-input"
              onSubmit={(event) => {
                event.preventDefault()
                sendMessage()
              }}
            >
              <textarea
                value={input}
                placeholder="问 DeepSeek：例如这个分割结果怎么写进科研汇报？"
                onChange={(event) => setInput(event.target.value)}
              />
              <button type="submit" disabled={chatLoading}>发送</button>
            </form>
          </section>

          <aside className="assistant-segmentation">
            <div className="assistant-kb-status">
              <h3>本地 PDF 知识库</h3>
              <p>
                {authorityStatus?.store_type || '-'} · chunks {authorityStatus?.indexed_chunks ?? '-'} ·
                {authorityStatus?.chroma_ready ? ' ChromaDB ready' : ' fallback/未就绪'}
              </p>
              <small>PDF 原文由用户手动放入项目；JSONL 是备份，正式检索优先 ChromaDB。</small>
            </div>

            <h3>上传图片进行分割</h3>
            <p>支持 PNG/JPG CT/MRI 切片，调用当前后端 `/predict` 和 epoch_241.pth 模型。</p>
            <input
              ref={fileRef}
              type="file"
              multiple
              accept="image/*"
              onChange={(event) => {
                setSegFiles(Array.from(event.target.files || []))
                setSegResults([])
              }}
            />
            <button type="button" onClick={runSegmentation} disabled={!segFiles.length || segLoading}>
              {segLoading ? '分割中...' : '开始分割'}
            </button>

            {activeSegResult && (
              <div className="assistant-seg-result">
                <img src={activeSegResult.image_base64} alt={`${activeSegResult.filename} segmentation`} />
                <div className="seg-result-toolbar">
                  {segResults.map((item, index) => (
                    <button
                      key={item.filename}
                      type="button"
                      className={index === segIndex ? 'active' : ''}
                      onClick={() => setSegIndex(index)}
                    >
                      {index + 1}
                    </button>
                  ))}
                </div>
                <strong>{activeSegResult.filename}</strong>
                <div className="seg-metric-tags">
                  {(activeSegResult.metrics || []).length ? (
                    activeSegResult.metrics.map((metric) => (
                      <span key={metric.organ}>{metric.organ}: {metric.percentage}</span>
                    ))
                  ) : (
                    <span>未检测到显著器官区域</span>
                  )}
                </div>
                <details className="seg-context-preview">
                  <summary>已传给 DeepSeek 的分割上下文</summary>
                  <pre>{segmentationContext}</pre>
                </details>
              </div>
            )}

            <small>安全提示：本功能仅用于科研辅助分析，不提供临床诊断。</small>
          </aside>
        </div>
      </div>
    </div>
  )
}
