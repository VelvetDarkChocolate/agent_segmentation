import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { analyzeSegmentationWithAuthority, getAuthorityStatus } from '../services/api'

const promptButtons = [
  '基于本地权威 PDF 生成科研汇报',
  '解释该切片的单切片局限性',
  '分析哪些器官需要人工复核',
  '解释 pixel_count 和 Dice/HD95 的区别',
]

function getInitialSegmentationResult(locationState) {
  if (locationState?.segmentationResult?.results) return locationState.segmentationResult
  try {
    const stored = JSON.parse(localStorage.getItem('latestSegmentationResult') || '{}')
    return stored?.results ? stored : null
  } catch {
    return null
  }
}

function summarizeSegmentation(result) {
  if (!result?.results?.length) return null
  const organSet = new Set()
  let total = 0
  result.results.forEach((slice) => {
    ;(slice.metrics || []).forEach((metric) => {
      organSet.add(metric.organ)
      const value = Number(String(metric.percentage || '0').replace('%', ''))
      if (!Number.isNaN(value)) total += value
    })
  })
  return {
    modelName: result.model_name || 'MMRSG-UNet epoch_241.pth',
    imageNames: result.results.map((item) => item.filename).join(', '),
    organCount: organSet.size,
    totalPercentage: total.toFixed(2),
  }
}

export default function ResearchAgent() {
  const location = useLocation()
  const [segmentationResult] = useState(() => getInitialSegmentationResult(location.state))
  const [authorityStatus, setAuthorityStatus] = useState(null)
  const [message, setMessage] = useState(promptButtons[0])
  const [response, setResponse] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const summary = useMemo(() => summarizeSegmentation(segmentationResult), [segmentationResult])

  useEffect(() => {
    getAuthorityStatus()
      .then((res) => setAuthorityStatus(res.data))
      .catch(() => setAuthorityStatus({ indexed_sources: 0, indexed_chunks: 0, store_type: 'unavailable', sources: [] }))
  }, [])

  async function runAnalysis(nextMessage = message) {
    if (!segmentationResult?.results?.length) {
      setError('请先在分割工作台完成 /predict 分割，再进入科研 Agent。')
      return
    }
    setLoading(true)
    setError('')
    try {
      const res = await analyzeSegmentationWithAuthority({
        message: nextMessage,
        segmentation_result: segmentationResult,
        top_k: 8,
        authority_only: true,
        min_authority_level: 4,
      })
      setResponse(res.data)
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Authority analysis failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="page research-agent-page">
      <div className="page-title">
        <span className="step">A</span>
        <div>
          <h2>Local-PDF Authority Segmentation-Grounded RAG Agent</h2>
          <p>本系统仅用于科研辅助分析，不提供临床诊断或治疗建议。</p>
        </div>
      </div>

      <div className="agent-layout">
        <aside className="card agent-side-panel">
          <h3>当前分割结果</h3>
          {summary ? (
            <dl className="agent-summary">
              <dt>模型名</dt>
              <dd>{summary.modelName}</dd>
              <dt>图像名</dt>
              <dd>{summary.imageNames}</dd>
              <dt>器官数量</dt>
              <dd>{summary.organCount}</dd>
              <dt>总面积占比</dt>
              <dd>{summary.totalPercentage}%</dd>
            </dl>
          ) : (
            <p className="empty">暂无 /predict 分割结果。</p>
          )}

          <h3>Authority PDF KB 状态</h3>
          <p className="hint">
            registered_sources: {authorityStatus?.registered_sources ?? '-'} · available_pdfs: {authorityStatus?.available_pdfs ?? '-'} · indexed_chunks: {authorityStatus?.indexed_chunks ?? '-'} · missing_pdfs: {(authorityStatus?.missing_pdfs || []).length}
          </p>
          {authorityStatus?.pdf_dir && <p className="hint">PDF dir: {authorityStatus.pdf_dir}</p>}

          <div className="agent-actions">
            {promptButtons.map((prompt) => (
              <button
                key={prompt}
                type="button"
                className="secondary-action"
                onClick={() => {
                  setMessage(prompt)
                  runAnalysis(prompt)
                }}
              >
                {prompt}
              </button>
            ))}
          </div>
        </aside>

        <main className="card agent-main-panel">
          <label>分析问题</label>
          <textarea value={message} onChange={(event) => setMessage(event.target.value)} />
          <button type="button" onClick={() => runAnalysis()} disabled={loading}>
            {loading ? '本地 PDF 知识库分析中...' : '基于本地权威 PDF 生成科研分析'}
          </button>
          {error && <p className="hint error">{error}</p>}

          {response && (
            <article className="agent-response">
              <h3>answer</h3>
              <pre>{response.answer}</pre>

              <h3>citations</h3>
              {(response.citations || []).length ? (
                response.citations.map((citation) => (
                  <div className="citation" key={citation.chunk_id}>
                    <strong>[{citation.source_id}] {citation.title}</strong>
                    <span>{citation.publisher} · pages {citation.page_start}-{citation.page_end} · authority_level {citation.authority_level}</span>
                    <a href={citation.source_url} target="_blank" rel="noreferrer">{citation.source_url}</a>
                    <p>{citation.section_title}: {citation.preview}</p>
                  </div>
                ))
              ) : (
                <p className="empty">当前本地权威 PDF 知识库中没有召回足够相关依据。</p>
              )}

              <h3>tools_used</h3>
              <div className="tool-tags">
                {(response.tools_used || []).map((tool) => <span key={tool}>{tool}</span>)}
              </div>

              <h3>segmentation_facts</h3>
              <pre>{JSON.stringify(response.segmentation_facts, null, 2)}</pre>

              <h3>authority_context</h3>
              <pre>{JSON.stringify(response.authority_context, null, 2)}</pre>
            </article>
          )}
        </main>
      </div>
    </section>
  )
}
