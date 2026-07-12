// Dünner API-Client für die Anwendungshinweise-REST-API.
//
// Die Basis-URL wird ermittelt aus:
//   1. VITE_API_BASE_URL (lokale Entwicklung, .env)
//   2. /config.json (im Deployment vom CDK in den S3-Bucket gelegt)

let cachedBase = null

export async function apiBaseUrl() {
  if (cachedBase !== null) return cachedBase
  const envUrl = import.meta.env.VITE_API_BASE_URL
  if (envUrl) {
    cachedBase = envUrl.replace(/\/$/, '')
    return cachedBase
  }
  try {
    const res = await fetch('/config.json', { cache: 'no-store' })
    const cfg = await res.json()
    cachedBase = (cfg.apiBaseUrl || '').replace(/\/$/, '')
  } catch (e) {
    cachedBase = ''
  }
  return cachedBase
}

async function request(path, options = {}) {
  const base = await apiBaseUrl()
  if (!base) {
    throw new Error(
      'Keine API-URL konfiguriert. VITE_API_BASE_URL setzen oder config.json bereitstellen.'
    )
  }
  const res = await fetch(base + path, options)
  let data = {}
  try {
    data = await res.json()
  } catch (e) {
    /* leere/nicht-JSON-Antwort */
  }
  if (!res.ok) {
    throw new Error(data.error || `HTTP ${res.status}`)
  }
  return data
}

export function askQuestion(question, sessionId) {
  return request('/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, sessionId }),
  })
}

export const listDocuments = () => request('/documents')
export const listIngestionJobs = () => request('/ingestion-jobs')
export const debugRetrieve = (q) =>
  request('/retrieve?q=' + encodeURIComponent(q))
