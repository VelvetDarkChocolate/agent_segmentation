import { useEffect, useState } from 'react'
import { api } from '../services/api'

export default function ResultReview() {
  const [reports, setReports] = useState([])

  async function loadReports() {
    const response = await api.get('/api/reports')
    setReports(response.data)
  }

  useEffect(() => {
    loadReports()
  }, [])

  return (
    <section className="page">
      <div className="page-title">
        <span className="step">4</span>
        <div>
          <h2>结果报告 / 质控审核</h2>
          <p>结果可追溯、人工复核、报告导出</p>
        </div>
      </div>

      <div className="toolbar">
        <button type="button" onClick={loadReports}>刷新报告</button>
        <button type="button">导出报告(PDF)</button>
      </div>

      {reports.length === 0 && (
        <div className="card empty">
          暂无报告。请先在分割工作台提交任务并等待完成。
        </div>
      )}

      {reports.map((report) => (
        <div className="card report" key={report.case_id}>
          <div className="report-layout">
            <div>
              <h3>病例ID: {report.case_id}</h3>
              <p>模型: {report.model_name}</p>
              <p>审核状态: {report.review.human_status}</p>

              <table>
                <thead>
                  <tr>
                    <th>类别</th>
                    <th>体积 cm³</th>
                    <th>占比</th>
                    <th>最大径 cm</th>
                  </tr>
                </thead>
                <tbody>
                  {report.organs.map((item) => (
                    <tr key={item.name}>
                      <td>{item.name}</td>
                      <td>{item.volume_cm3}</td>
                      <td>{item.ratio}</td>
                      <td>{item.max_diameter_cm}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <aside className="review-flow">
              <span>影像上传</span>
              <span>AI 初筛完成</span>
              <span>人工复核</span>
              <span>结果归档</span>
            </aside>
          </div>
        </div>
      ))}
    </section>
  )
}
