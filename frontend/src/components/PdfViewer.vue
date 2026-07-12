<script setup>
// Eingebetteter PDF-Viewer (PDF.js): rendert die Zielseite und hebt das
// wörtlich zitierte Textstück hervor (Textsuche in der PDF-Textebene).
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as pdfjsLib from 'pdfjs-dist'
import PdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?worker'

pdfjsLib.GlobalWorkerOptions.workerPort = new PdfWorker()

const props = defineProps({
  pdfUrl: { type: String, required: true },
  page: { type: Number, default: 1 },
  quote: { type: String, default: '' },
  document: { type: String, default: '' },
})
const emit = defineEmits(['close'])

const wrap = ref(null)
const canvas = ref(null)
const loading = ref(true)
const error = ref('')
const highlights = ref([])
const highlightFound = ref(false)
const pageDims = ref({ width: 0, height: 0 })

let pdfDoc = null
let loadedUrl = null

function normalize(text) {
  return (text || '')
    .toLowerCase()
    .replace(/­/g, '') // Weiches Trennzeichen
    .replace(/\s+/g, ' ')
    .trim()
}

function computeHighlights(textContent, viewport) {
  const items = textContent.items.filter((i) => typeof i.str === 'string')
  let pageStr = ''
  const ranges = []
  for (const it of items) {
    const t = normalize(it.str)
    if (!t) {
      ranges.push(null)
      continue
    }
    const start = pageStr.length
    pageStr += t
    ranges.push([start, pageStr.length])
    pageStr += ' '
  }

  const q = normalize(props.quote)
  let target = q
  let idx = q ? pageStr.indexOf(target) : -1
  // Fallback: nur den Anfang des Zitats suchen (Zitate können länger sein
  // als der auf dieser Seite liegende Teil).
  if (idx < 0 && q.length > 60) {
    target = q.slice(0, 60)
    idx = pageStr.indexOf(target)
  }
  if (idx < 0) {
    highlightFound.value = false
    return
  }

  const mStart = idx
  const mEnd = idx + target.length
  const boxes = []
  items.forEach((it, i) => {
    const r = ranges[i]
    if (!r || r[1] <= mStart || r[0] >= mEnd) return
    const tx = pdfjsLib.Util.transform(viewport.transform, it.transform)
    const fontHeight = Math.hypot(tx[2], tx[3])
    boxes.push({
      left: tx[4],
      top: tx[5] - fontHeight,
      width: (it.width || 0) * viewport.scale || 2,
      height: fontHeight,
    })
  })
  highlights.value = boxes
  highlightFound.value = boxes.length > 0
}

async function render() {
  loading.value = true
  error.value = ''
  highlights.value = []
  highlightFound.value = false
  try {
    if (loadedUrl !== props.pdfUrl) {
      if (pdfDoc) await pdfDoc.destroy()
      pdfDoc = await pdfjsLib.getDocument({ url: props.pdfUrl }).promise
      loadedUrl = props.pdfUrl
    }
    const pageNum = Math.min(Math.max(props.page || 1, 1), pdfDoc.numPages)
    const pageObj = await pdfDoc.getPage(pageNum)

    await nextTick()
    const containerWidth = wrap.value ? wrap.value.clientWidth - 4 : 800
    const unscaled = pageObj.getViewport({ scale: 1 })
    const scale = Math.min(2, Math.max(0.5, containerWidth / unscaled.width))
    const viewport = pageObj.getViewport({ scale })
    pageDims.value = { width: viewport.width, height: viewport.height }

    const cv = canvas.value
    const ctx = cv.getContext('2d')
    cv.width = viewport.width
    cv.height = viewport.height
    await pageObj.render({ canvasContext: ctx, viewport }).promise

    if (props.quote) {
      computeHighlights(await pageObj.getTextContent(), viewport)
      await nextTick()
      scrollToHighlight()
    }
  } catch (e) {
    error.value = e && e.message ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

function scrollToHighlight() {
  if (!highlights.value.length || !wrap.value) return
  const top = Math.min(...highlights.value.map((h) => h.top))
  wrap.value.scrollTop = Math.max(0, top - 80)
}

watch(() => [props.pdfUrl, props.page, props.quote], render)
onMounted(render)
onBeforeUnmount(async () => {
  if (pdfDoc) await pdfDoc.destroy()
})
</script>

<template>
  <div class="pdf-modal" @click.self="emit('close')">
    <div class="pdf-dialog">
      <header class="pdf-head">
        <span class="pdf-title">{{ document }} · Seite {{ page }}</span>
        <span class="pdf-actions">
          <a :href="pdfUrl + '#page=' + page" target="_blank" rel="noopener">Im Tab öffnen ↗</a>
          <button type="button" @click="emit('close')" aria-label="Schließen">✕</button>
        </span>
      </header>

      <div class="pdf-body" ref="wrap">
        <p v-if="loading" class="pdf-note">Lade PDF …</p>
        <p v-if="error" class="pdf-error">PDF konnte nicht geladen werden: {{ error }}</p>
        <p v-if="!loading && !error && quote && !highlightFound" class="pdf-note">
          Zitat auf dieser Seite nicht exakt gefunden – Seite unmarkiert angezeigt.
        </p>
        <div
          v-show="!loading && !error"
          class="pdf-canvas-wrap"
          :style="{ width: pageDims.width + 'px', height: pageDims.height + 'px' }"
        >
          <canvas ref="canvas"></canvas>
          <div class="hl-layer">
            <div
              v-for="(h, i) in highlights"
              :key="i"
              class="hl"
              :style="{
                left: h.left + 'px',
                top: h.top + 'px',
                width: h.width + 'px',
                height: h.height + 'px',
              }"
            ></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pdf-modal {
  position: fixed;
  inset: 0;
  background: rgba(20, 28, 36, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  z-index: 100;
}
.pdf-dialog {
  background: #fff;
  width: min(900px, 100%);
  max-height: 92vh;
  display: flex;
  flex-direction: column;
  border-radius: var(--radius);
  overflow: hidden;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.3);
}
.pdf-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  padding: 0.6rem 0.9rem;
  background: var(--brand);
  color: #fff;
}
.pdf-title {
  font-weight: 600;
  font-size: 0.95rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pdf-actions {
  display: flex;
  align-items: center;
  gap: 0.8rem;
  flex: none;
}
.pdf-actions a {
  color: #fff;
  text-decoration: underline;
  font-size: 0.85rem;
}
.pdf-actions button {
  background: rgba(255, 255, 255, 0.2);
  border: none;
  color: #fff;
  width: 1.8rem;
  height: 1.8rem;
  border-radius: var(--radius);
  font-size: 1rem;
}
.pdf-body {
  overflow: auto;
  padding: 0.75rem;
  background: #55606b;
  display: flex;
  justify-content: center;
}
.pdf-canvas-wrap {
  position: relative;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.35);
}
.pdf-canvas-wrap canvas {
  display: block;
}
.hl-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.hl {
  position: absolute;
  background: var(--mark);
  opacity: 0.42;
  mix-blend-mode: multiply;
  border-radius: 1px;
}
.pdf-note {
  color: #fff;
  align-self: center;
}
.pdf-error {
  color: #ffd7d7;
  align-self: center;
}
</style>
