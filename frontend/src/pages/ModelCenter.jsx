import { useEffect, useState } from 'react'
import { api } from '../services/api'

export default function ModelCenter() {
  const [models, setModels] = useState([])

  useEffect(() => {
    api.get('/api/models').then((response) => setModels(response.data))
  }, [])

  return (
    <section className="page">
      <div className="page-title">
        <span className="step">3</span>
        <div>
          <h2>模型中心 / 训练与评估</h2>
          <p>多模型管理、版本评估、训练任务追踪</p>
        </div>
      </div>

      <div className="card">
        <div className="card-heading">
          <h3>模型管理</h3>
          <button type="button">新建训练任务</button>
        </div>
        <table>
          <thead>
            <tr>
              <th>模型名称</th>
              <th>任务类型</th>
              <th>Dice</th>
              <th>HD95</th>
              <th>版本</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {models.map((model) => (
              <tr key={model.name}>
                <td>{model.name}</td>
                <td>{model.body_part}</td>
                <td>{model.dice}</td>
                <td>{model.hd95}</td>
                <td>{model.version}</td>
                <td><span className="status">{model.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="model-grid">
        <div className="card chart-card">
          <h3>模型性能趋势 Dice</h3>
          <div className="line-chart">
            <div style={{ height: '38%' }}></div>
            <div style={{ height: '30%' }}></div>
            <div style={{ height: '25%' }}></div>
            <div style={{ height: '20%' }}></div>
            <div style={{ height: '17%' }}></div>
          </div>
        </div>
        <div className="card training-card">
          <h3>当前训练任务</h3>
          <p>实验模型 A（肿瘤分割）</p>
          <div className="progress"><div style={{ width: '68%' }}></div></div>
          <dl>
            <div><dt>运行时长</dt><dd>2d 14h 32m</dd></div>
            <div><dt>剩余时间</dt><dd>10h 06m</dd></div>
            <div><dt>GPU 占用</dt><dd>2 / 4</dd></div>
          </dl>
        </div>
      </div>
    </section>
  )
}
