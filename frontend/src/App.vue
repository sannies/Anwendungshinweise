<script setup>
import { ref, onMounted } from 'vue'
import {
  askQuestion,
  listDocuments,
  listIngestionJobs,
  debugRetrieve,
} from './api.js'
import PdfViewer from './components/PdfViewer.vue'

const EXAMPLES = [
  'Ich habe eine neue Kalksandsteinfassade ohne Wärmedämmung und möchte die Dämmung verkleben. Muss ich die Fassade vorher grundieren?',
  'Ich habe losen Putz auf einer Wärmedämmverbundfassade und bin mit der Sanierung beauftragt. Wie gehe ich vor?',
]

const tab = ref('frage')

// Eingebetteter PDF-Viewer (Zitat-Hervorhebung)
const viewer = ref(null)
function openViewer(item) {
  if (!item || !item.pdfUrl) return
  viewer.value = {
    pdfUrl: item.pdfUrl,
    page: item.page || 1,
    quote: item.snippet || '',
    document: item.document || '',
  }
}

// --- Frage stellen ---------------------------------------------------------
const question = ref('')
const answer = ref(null)
const asking = ref(false)
const askError = ref('')
const sessionId = ref(null)

async function submitQuestion() {
  const q = question.value.trim()
  if (!q) return
  asking.value = true
  askError.value = ''
  answer.value = null
  try {
    const res = await askQuestion(q, sessionId.value)
    answer.value = res
    sessionId.value = res.sessionId || null
  } catch (e) {
    askError.value = e.message
  } finally {
    asking.value = false
  }
}

function useExample(text) {
  question.value = text
  tab.value = 'frage'
}

function resetSession() {
  sessionId.value = null
  answer.value = null
}

// --- Wissensbasis ----------------------------------------------------------
const documents = ref([])
const jobs = ref([])
const kbLoading = ref(false)
const kbError = ref('')

async function loadKnowledgeBase() {
  kbLoading.value = true
  kbError.value = ''
  try {
    const [docs, ing] = await Promise.all([listDocuments(), listIngestionJobs()])
    documents.value = docs.documents || []
    jobs.value = ing.jobs || []
  } catch (e) {
    kbError.value = e.message
  } finally {
    kbLoading.value = false
  }
}

// --- Debug: Retrieval -------------------------------------------------------
const debugQuery = ref('')
const debugResults = ref([])
const debugLoading = ref(false)

async function runDebug() {
  const q = debugQuery.value.trim()
  if (!q) return
  debugLoading.value = true
  debugResults.value = []
  try {
    const res = await debugRetrieve(q)
    debugResults.value = res.results || []
  } catch (e) {
    alert('Fehler: ' + e.message)
  } finally {
    debugLoading.value = false
  }
}

function formatBytes(n) {
  if (!n && n !== 0) return '–'
  if (n < 1024) return n + ' B'
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB'
  return (n / 1024 / 1024).toFixed(1) + ' MB'
}

onMounted(loadKnowledgeBase)
</script>

<template>
  <div class="app">
    <header class="site-header">
      <div class="topbar">
        <div class="container">Wissensdatenbank · Maler- und Lackiererhandwerk</div>
      </div>
      <div class="brandbar">
        <div class="container brand-inner">
          <div class="logo">
            <span class="logo-mark">MV</span>
            <span class="logo-words">
              <strong>Anwendungshinweise</strong>
              <small>Merkblätter-Wissensbasis (Demo)</small>
            </span>
          </div>
          <nav class="tabs">
            <button :class="{ active: tab === 'frage' }" @click="tab = 'frage'">
              Frage stellen
            </button>
            <button
              :class="{ active: tab === 'wissen' }"
              @click="tab = 'wissen'; loadKnowledgeBase()"
            >
              Wissensbasis
            </button>
            <button :class="{ active: tab === 'debug' }" @click="tab = 'debug'">
              Debug
            </button>
          </nav>
        </div>
      </div>
    </header>

    <main class="container content">
      <!-- ===================== FRAGE ===================== -->
      <section v-show="tab === 'frage'" class="panel">
        <h2>Fachfrage stellen</h2>
        <p class="lead">
          Antworten kommen <strong>ausschließlich</strong> aus den hinterlegten
          Anwendungshinweisen – mit wörtlichen Zitaten und Verweis auf Dokument
          und Seite.
        </p>

        <form @submit.prevent="submitQuestion">
          <textarea
            v-model="question"
            rows="3"
            placeholder="z. B. Muss ich eine neue Kalksandsteinfassade vor dem Verkleben der Dämmung grundieren?"
          ></textarea>
          <div class="row">
            <button type="submit" class="btn-primary" :disabled="asking">
              {{ asking ? 'Suche in den Merkblättern …' : 'Frage beantworten' }}
            </button>
            <button v-if="sessionId" type="button" class="btn-ghost" @click="resetSession">
              Neues Gespräch
            </button>
          </div>
        </form>

        <div class="examples">
          <span>Beispiele:</span>
          <button v-for="ex in EXAMPLES" :key="ex" class="chip" @click="useExample(ex)">
            {{ ex.slice(0, 58) }}…
          </button>
        </div>

        <p v-if="askError" class="error">{{ askError }}</p>

        <div v-if="answer" class="answer">
          <div v-if="answer.warning || answer.grounded === false" class="warning">
            ⚠️ {{ answer.warning || 'Kein ausreichender Treffer in den Anwendungshinweisen gefunden – die Antwort ist nicht durch Quellen belegt.' }}
          </div>
          <h3>Antwort</h3>
          <p class="answer-text">{{ answer.answer }}</p>

          <div v-if="answer.citations && answer.citations.length" class="belege">
            <h4>Belege (wörtliche Zitate)</h4>
            <p class="hint">Klick auf „Im PDF anzeigen" öffnet die Fundstelle und markiert sie.</p>
            <div v-for="(c, i) in answer.citations" :key="i" class="beleg">
              <blockquote>„{{ c.snippet }}"</blockquote>
              <div class="beleg-foot">
                <span class="src">{{ c.document }}<template v-if="c.page"> · Seite {{ c.page }}</template></span>
                <button v-if="c.pdfUrl" class="btn-small" @click="openViewer(c)">
                  Im PDF anzeigen
                </button>
              </div>
            </div>
          </div>

          <div v-if="answer.sources && answer.sources.length" class="sources">
            <h4>Verwendete Dokumente</h4>
            <ul>
              <li v-for="s in answer.sources" :key="s.uri">
                📄
                <a v-if="s.link" :href="s.link" target="_blank" rel="noopener">{{ s.document }}</a>
                <span v-else>{{ s.document }}</span>
                <span v-if="s.pages && s.pages.length" class="pages">
                  · Seite {{ s.pages.join(', ') }}
                </span>
              </li>
            </ul>
          </div>
        </div>
      </section>

      <!-- ===================== WISSENSBASIS ===================== -->
      <section v-show="tab === 'wissen'" class="panel">
        <div class="row space">
          <h2>Indizierte Dokumente</h2>
          <button class="btn-ghost" @click="loadKnowledgeBase" :disabled="kbLoading">
            Aktualisieren
          </button>
        </div>
        <p v-if="kbError" class="error">{{ kbError }}</p>
        <p v-if="kbLoading" class="muted">Lade …</p>

        <table v-if="documents.length">
          <thead>
            <tr><th>Dokument</th><th>Größe</th><th>Zuletzt geändert</th></tr>
          </thead>
          <tbody>
            <tr v-for="d in documents" :key="d.key">
              <td>{{ d.document }}</td>
              <td>{{ formatBytes(d.size) }}</td>
              <td>{{ d.lastModified }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else-if="!kbLoading" class="muted">
          Noch keine Dokumente. PDFs in den S3-Bucket (Prefix <code>documents/</code>)
          hochladen – die Indizierung startet automatisch.
        </p>

        <h2 class="mt">Indizierungs-Läufe</h2>
        <table v-if="jobs.length">
          <thead>
            <tr><th>Status</th><th>Neu indiziert</th><th>Gestartet</th></tr>
          </thead>
          <tbody>
            <tr v-for="j in jobs" :key="j.ingestionJobId">
              <td><span class="badge" :data-status="j.status">{{ j.status }}</span></td>
              <td>{{ j.statistics?.numberOfNewDocumentsIndexed ?? '–' }}</td>
              <td>{{ j.startedAt }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else-if="!kbLoading" class="muted">Noch keine Läufe.</p>
      </section>

      <!-- ===================== DEBUG ===================== -->
      <section v-show="tab === 'debug'" class="panel">
        <h2>Retrieval-Debug</h2>
        <p class="muted">
          Rohe Treffer der Vektorsuche (mit Score), ohne Generierung – zeigt,
          welche Passagen gefunden werden.
        </p>
        <form @submit.prevent="runDebug" class="row">
          <input v-model="debugQuery" placeholder="Suchbegriff / Frage …" />
          <button type="submit" class="btn-primary" :disabled="debugLoading">Suchen</button>
        </form>

        <div v-for="(r, i) in debugResults" :key="i" class="hit">
          <div class="row space">
            <strong>{{ r.document }}<template v-if="r.page"> · S. {{ r.page }}</template></strong>
            <span class="hit-right">
              <span class="score">Score: {{ r.score?.toFixed(3) }}</span>
              <button v-if="r.pdfUrl" class="btn-small" @click="openViewer(r)">Im PDF</button>
            </span>
          </div>
          <p>{{ r.snippet }}</p>
        </div>
      </section>
    </main>

    <footer class="site-footer">
      <div class="container">
        Demo · Amazon Bedrock Knowledge Base + S3 Vectors · Region eu-central-1
      </div>
    </footer>

    <PdfViewer v-if="viewer" v-bind="viewer" @close="viewer = null" />
  </div>
</template>

<style scoped>
.container {
  max-width: 960px;
  margin: 0 auto;
  padding: 0 1rem;
}

/* Header */
.topbar {
  background: var(--brand-dark);
  color: #cfe0ef;
  font-size: 0.8rem;
}
.topbar .container {
  padding-top: 0.35rem;
  padding-bottom: 0.35rem;
}
.brandbar {
  background: var(--brand);
  color: #fff;
}
.brand-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.5rem;
  padding-top: 0.6rem;
  padding-bottom: 0.6rem;
}
.logo {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}
.logo-mark {
  background: #fff;
  color: var(--brand);
  font-weight: 800;
  letter-spacing: 0.5px;
  padding: 0.3rem 0.5rem;
  border-radius: var(--radius);
  font-size: 1.1rem;
}
.logo-words {
  display: flex;
  flex-direction: column;
  line-height: 1.1;
}
.logo-words strong {
  font-size: 1.15rem;
}
.logo-words small {
  font-size: 0.72rem;
  color: #cfe0ef;
}
.tabs {
  display: flex;
  gap: 0.25rem;
}
.tabs button {
  background: rgba(255, 255, 255, 0.12);
  border: none;
  color: #fff;
  padding: 0.5rem 0.9rem;
  border-radius: var(--radius);
  font-size: 0.9rem;
}
.tabs button.active {
  background: #fff;
  color: var(--brand-dark);
  font-weight: 700;
}

.content {
  padding-top: 1.25rem;
  padding-bottom: 2rem;
}

.panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-top: 3px solid var(--brand);
  border-radius: var(--radius);
  padding: 1.25rem 1.4rem;
}
.panel h2 {
  margin: 0 0 0.5rem;
  font-size: 1.25rem;
  color: var(--brand-dark);
}
.lead {
  margin: 0 0 1rem;
  color: var(--muted);
}

textarea,
input {
  width: 100%;
  padding: 0.7rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  font: inherit;
  resize: vertical;
}
textarea:focus,
input:focus {
  outline: 2px solid var(--brand-light);
  border-color: var(--brand);
}

.row {
  display: flex;
  gap: 0.6rem;
  align-items: center;
  margin-top: 0.75rem;
}
.row.space {
  justify-content: space-between;
}

.btn-primary {
  background: var(--brand);
  color: #fff;
  border: none;
  padding: 0.6rem 1.2rem;
  border-radius: var(--radius);
  font-weight: 600;
}
.btn-primary:hover {
  background: var(--brand-dark);
}
.btn-primary:disabled {
  opacity: 0.6;
  cursor: default;
}
.btn-ghost {
  background: none;
  border: 1px solid var(--border);
  padding: 0.5rem 0.9rem;
  border-radius: var(--radius);
  color: var(--muted);
}
.btn-small {
  background: var(--brand-light);
  border: 1px solid var(--brand);
  color: var(--brand-dark);
  padding: 0.3rem 0.7rem;
  border-radius: var(--radius);
  font-size: 0.8rem;
  font-weight: 600;
  flex: none;
}
.btn-small:hover {
  background: var(--brand);
  color: #fff;
}

.examples {
  margin-top: 1rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  align-items: center;
  color: var(--muted);
  font-size: 0.9rem;
}
.chip {
  background: var(--brand-light);
  border: 1px solid var(--border);
  color: var(--brand-dark);
  padding: 0.35rem 0.6rem;
  border-radius: 999px;
  font-size: 0.8rem;
}

.answer {
  margin-top: 1.25rem;
  border-top: 1px solid var(--border);
  padding-top: 1rem;
}
.answer h3 {
  margin: 0 0 0.5rem;
  color: var(--brand-dark);
}
.answer-text {
  white-space: pre-wrap;
  line-height: 1.6;
}

.belege {
  margin-top: 1.25rem;
}
.belege h4,
.sources h4 {
  margin: 0 0 0.3rem;
  font-size: 1rem;
}
.hint {
  color: var(--muted);
  font-size: 0.8rem;
  margin: 0 0 0.6rem;
}
.beleg {
  border: 1px solid var(--border);
  border-left: 3px solid var(--brand);
  border-radius: var(--radius);
  padding: 0.6rem 0.8rem;
  margin-bottom: 0.6rem;
  background: #fafcfe;
}
.beleg blockquote {
  margin: 0 0 0.5rem;
  font-size: 0.92rem;
  color: #2b3742;
}
.beleg-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.6rem;
}
.beleg-foot .src {
  font-size: 0.78rem;
  color: var(--muted);
}

.sources {
  margin-top: 1.25rem;
}
.sources ul {
  margin: 0;
  padding-left: 0;
  list-style: none;
}
.sources li {
  padding: 0.15rem 0;
}
.pages {
  color: var(--muted);
  font-size: 0.85rem;
}

table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 0.5rem;
  font-size: 0.9rem;
}
th,
td {
  text-align: left;
  padding: 0.5rem;
  border-bottom: 1px solid var(--border);
}
th {
  color: var(--muted);
  font-weight: 700;
  background: #f6f8fa;
}
.badge {
  padding: 0.15rem 0.5rem;
  border-radius: var(--radius);
  font-size: 0.75rem;
  background: var(--brand-light);
  color: var(--brand-dark);
}
.badge[data-status='COMPLETE'] {
  background: #e6f4ea;
  color: var(--ok);
}
.badge[data-status='FAILED'] {
  background: #fde8e8;
  color: var(--danger);
}

.hit {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0.7rem 0.9rem;
  margin-top: 0.7rem;
}
.hit p {
  margin: 0.4rem 0 0;
  font-size: 0.9rem;
}
.hit-right {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}
.score {
  color: var(--muted);
  font-size: 0.8rem;
}

.muted {
  color: var(--muted);
}
.mt {
  margin-top: 1.5rem;
}
.error {
  color: var(--danger);
  background: #fde8e8;
  padding: 0.6rem 0.8rem;
  border-radius: var(--radius);
  margin-top: 0.75rem;
}
.warning {
  color: var(--warn);
  background: #fff7e0;
  border: 1px solid #f0d68a;
  border-left: 3px solid var(--warn);
  padding: 0.7rem 0.9rem;
  border-radius: var(--radius);
  margin-bottom: 0.9rem;
  font-weight: 600;
}

.site-footer {
  border-top: 1px solid var(--border);
  color: var(--muted);
  font-size: 0.8rem;
  padding: 1rem 0;
  text-align: center;
}
</style>
