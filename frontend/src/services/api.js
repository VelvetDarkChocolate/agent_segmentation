import axios from 'axios'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 30000,
})

export function getAuthorityStatus() {
  return api.get('/api/agent/authority/status')
}

export function analyzeSegmentationWithAuthority(payload) {
  return api.post('/api/agent/segmentation/analyze', payload, { timeout: 120000 })
}
