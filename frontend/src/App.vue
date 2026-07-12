<script setup>
import { ref, onMounted } from 'vue'
import {
  askQuestion,
  listDocuments,
  listIngestionJobs,
  debugRetrieve,
} from './api.js'

const EXAMPLES = [
  'Ich habe eine neue Kalksandsteinfassade ohne Wärmedämmung und möchte die Dämmung verkleben. Muss ich die Fassade vorher grundieren?',
  'Ich habe losen Putz auf einer Wärmedämmverbundfassade und bin mit der Sanierung beauftragt. Wie gehe ich vor?',
]

const tab = ref('frage')

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
  <div class="wrap">
    <header>
      <h1>Anwendungshinweise-Wissensbasis</h1>
      <p class="subtitle">
        Fachfragen zum Maler- und Lackiererhandwerk – beantwortet
        <strong>ausschließlich</strong> aus den hinterlegten Merkblättern (Demo).
      </p>
    </header>

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

    <!-- ===================== FRAGE ===================== -->
    <section v-show="tab === 'frage'" class="panel">
      <form @submit.prevent="submitQuestion">
        <textarea
          v-model="question"
          rows="3"
          placeholder="z. B. Muss ich eine neue Kalksandsteinfassade vor dem Verkleben der Dämmung grundieren?"
        ></textarea>
        <div class="row">
          <button type="submit" class="primary" :disabled="asking">
            {{ asking ? 'Suche in den Merkblättern …' : 'Frage beantworten' }}
          </button>
          <button
            v-if="sessionId"
            type="button"
            class="ghost"
            @click="resetSession"
          >
            Neues Gespräch
          </button>
        </div>
      </form>

      <div class="examples">
        <span>Beispiele:</span>
        <button v-for="ex in EXAMPLES" :key="ex" class="chip" @click="useExample(ex)">
          {{ ex.slice(0, 60) }}…
        </button>
      </div>

      <p v-if="askError" class="error">{{ askError }}</p>

      <div v-if="answer" class="answer">
        <h2>Antwort</h2>
        <p class="answer-text">{{ answer.answer }}</p>

        <div v-if="answer.sources && answer.sources.length" class="sources">
          <h3>Quellen ({{ answer.sources.length }})</h3>
          <ul>
            <li v-for="s in answer.sources" :key="s.uri">
              📄 <strong>{{ s.document }}</strong>
            </li>
          </ul>
        </div>

        <details v-if="answer.citations && answer.citations.length">
          <summary>Belegstellen anzeigen ({{ answer.citations.length }})</summary>
          <blockquote v-for="(c, i) in answer.citations" :key="i">
            <div class="cite-doc">{{ c.document }}</div>
            {{ c.snippet }}
          </blockquote>
        </details>
      </div>
    </section>

    <!-- ===================== WISSENSBASIS ===================== -->
    <section v-show="tab === 'wissen'" class="panel">
      <div class="row space">
        <h2>Indizierte Dokumente</h2>
        <button class="ghost" @click="loadKnowledgeBase" :disabled="kbLoading">
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
            <td>
              <span class="badge" :data-status="j.status">{{ j.status }}</span>
            </td>
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
        Zeigt die rohen Treffer aus der Vektorsuche (mit Score) – ohne Generierung.
        Nützlich, um zu sehen, welche Passagen gefunden werden.
      </p>
      <form @submit.prevent="runDebug" class="row">
        <input v-model="debugQuery" placeholder="Suchbegriff / Frage …" />
        <button type="submit" class="primary" :disabled="debugLoading">Suchen</button>
      </form>

      <div v-for="(r, i) in debugResults" :key="i" class="hit">
        <div class="row space">
          <strong>{{ r.document }}</strong>
          <span class="score">Score: {{ r.score?.toFixed(3) }}</span>
        </div>
        <p>{{ r.snippet }}</p>
      </div>
    </section>

    <footer>
      Demo · Amazon Bedrock Knowledge Base + S3 Vectors · Region eu-central-1
    </footer>
  </div>
</template>

<style scoped>
.wrap {
  max-width: 820px;
  margin: 0 auto;
  padding: 1.5rem 1rem 3rem;
}
header h1 {
  margin: 0 0 0.25rem;
  font-size: 1.6rem;
}
.subtitle {
  margin: 0;
  color: var(--muted);
}
.tabs {
  display: flex;
  gap: 0.5rem;
  margin: 1.25rem 0 1rem;
  border-bottom: 1px solid var(--border);
}
.tabs button {
  background: none;
  border: none;
  padding: 0.6rem 0.9rem;
  color: var(--muted);
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}
.tabs button.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
  font-weight: 600;
}
.panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 1.25rem;
}
textarea,
input {
  width: 100%;
  padding: 0.7rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  font: inherit;
  resize: vertical;
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
button.primary {
  background: var(--accent);
  color: #fff;
  border: none;
  padding: 0.6rem 1.1rem;
  border-radius: 8px;
}
button.primary:disabled {
  opacity: 0.6;
  cursor: default;
}
button.ghost {
  background: none;
  border: 1px solid var(--border);
  padding: 0.5rem 0.9rem;
  border-radius: 8px;
  color: var(--muted);
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
  background: var(--accent-soft);
  border: none;
  color: var(--accent);
  padding: 0.35rem 0.6rem;
  border-radius: 999px;
  font-size: 0.8rem;
}
.answer {
  margin-top: 1.25rem;
  border-top: 1px solid var(--border);
  padding-top: 1rem;
}
.answer-text {
  white-space: pre-wrap;
  line-height: 1.55;
}
.sources ul {
  margin: 0.25rem 0 0;
  padding-left: 0;
  list-style: none;
}
.sources li {
  padding: 0.15rem 0;
}
blockquote {
  margin: 0.6rem 0;
  padding: 0.5rem 0.8rem;
  background: var(--bg);
  border-left: 3px solid var(--border);
  border-radius: 4px;
  font-size: 0.9rem;
}
.cite-doc {
  font-size: 0.75rem;
  color: var(--muted);
  margin-bottom: 0.25rem;
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
  padding: 0.45rem 0.5rem;
  border-bottom: 1px solid var(--border);
}
th {
  color: var(--muted);
  font-weight: 600;
}
.badge {
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  font-size: 0.75rem;
  background: var(--accent-soft);
  color: var(--accent);
}
.badge[data-status='COMPLETE'] {
  background: #e6f4ea;
  color: var(--ok);
}
.badge[data-status='FAILED'] {
  background: #fde8e8;
  color: #b42318;
}
.hit {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.7rem 0.9rem;
  margin-top: 0.7rem;
}
.hit p {
  margin: 0.4rem 0 0;
  font-size: 0.9rem;
  line-height: 1.45;
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
  color: #b42318;
  background: #fde8e8;
  padding: 0.6rem 0.8rem;
  border-radius: 8px;
}
footer {
  text-align: center;
  color: var(--muted);
  font-size: 0.8rem;
  margin-top: 1.5rem;
}
</style>
