<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, ApiError } from './api'
import type {
  BlastScope,
  OutcomeDetail,
  Revision,
  StoryboardSpec,
} from './types'
import StoryboardEditor from './components/StoryboardEditor.vue'
import OutcomeGrid from './components/OutcomeGrid.vue'
import RoutePair from './components/RoutePair.vue'
import TimelineCanvas from './components/TimelineCanvas.vue'

const revision = ref<Revision | null>(null)
const revisions = ref<{ revision_id: number; created_at: string; title: string; spec_hash: string; edit_note: string }[]>([])
const draft = ref<StoryboardSpec | null>(null)
const previewProof = ref<Revision['proof'] | null>(null)
const previewBlast = ref<BlastScope | null>(null)
const selectedOutcome = ref<OutcomeDetail | null>(null)
const selectedIndex = ref<number | null>(null)
const busy = ref(false)
const error = ref('')
const samples = ref<Record<string, { title: string; spec: StoryboardSpec }>>({})

// 每个异步代次：响应回来时若编号过期就丢弃，绝不贴到新修订上。
let previewToken = 0
let detailToken = 0

const proof = computed(() => previewProof.value ?? revision.value?.proof ?? null)

// 草稿相对当前修订是否已改动；改动中只展示预演影响域，不沿用父修订的旧域。
const draftDirty = computed(() => {
  if (!draft.value || !revision.value) return Boolean(draft.value)
  return JSON.stringify(draft.value) !== JSON.stringify(revision.value.spec)
})
const activeBlast = computed(() =>
  draftDirty.value ? previewBlast.value : revision.value?.changes_from_parent ?? null,
)

onMounted(async () => {
  samples.value = await api.samples()
  await refreshList()
  try {
    revision.value = await api.latest()
    draft.value = structuredClone(revision.value.spec)
  } catch {
    // 空库：载入第一个样例草稿但不落库。
    const first = Object.values(samples.value)[0]
    if (first) draft.value = structuredClone(first.spec)
  }
})

async function refreshList() {
  revisions.value = (await api.revisions()).revisions
}

function revisionCreated(rev: Revision) {
  revision.value = rev
  draft.value = structuredClone(rev.spec)
  previewProof.value = null
  previewBlast.value = null
  selectedIndex.value = null
  selectedOutcome.value = null
}

async function loadSample(key: string) {
  const sample = samples.value[key]
  if (!sample) return
  draft.value = structuredClone(sample.spec)
  previewProof.value = null
  previewBlast.value = null
  error.value = ''
  // 作为新修订提交，便于随后编辑出修订链。
  await commitDraft(sample.spec, `载入示例：${key}`)
}

async function onEdit(spec: StoryboardSpec) {
  draft.value = spec
  const token = ++previewToken
  selectedOutcome.value = null
  selectedIndex.value = null
  try {
    const [p] = await Promise.all([api.preview(spec)])
    if (token !== previewToken) return // 旧异步响应：丢弃
    previewProof.value = p
    // 影响域必须相对某个已冻结修订；没有修订时不预演。
    if (revision.value && JSON.stringify(spec) !== JSON.stringify(revision.value.spec)) {
      const blast = await api.blastPreview(revision.value.revision_id, spec)
      if (token !== previewToken) return
      previewBlast.value = blast
    } else {
      previewBlast.value = null
    }
  } catch (err) {
    if (token !== previewToken) return
    if (err instanceof ApiError) {
      error.value = err.message
      previewProof.value = null
      previewBlast.value = null
    }
  }
}

async function commitDraft(spec: StoryboardSpec, note: string) {
  if (!spec) return
  error.value = ''
  busy.value = true
  try {
    const rev = await api.commit(spec, revision.value?.revision_id ?? null, note)
    revisionCreated(rev)
    await refreshList()
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : String(err)
  } finally {
    busy.value = false
  }
}

async function openRevision(id: number) {
  busy.value = true
  const token = ++detailToken
  previewToken++
  try {
    const rev = await api.revision(id)
    revision.value = rev
    draft.value = structuredClone(rev.spec)
    previewProof.value = null
    selectedIndex.value = null
    selectedOutcome.value = null
  } finally {
    busy.value = false
    void token
  }
}

async function selectOutcome(index: number) {
  if (!revision.value) {
    error.value = '请先把故事板提交为修订，结局详情只挂在冻结校样上。'
    return
  }
  if (draftDirty.value) {
    error.value = '当前是未提交草稿的预演；请先提交为新修订再打开结局详情。'
    return
  }
  error.value = ''
  selectedIndex.value = index
  const token = ++detailToken
  selectedOutcome.value = null
  try {
    const detail = await api.outcome(revision.value.revision_id, index)
    if (token !== detailToken) return // 旧异步响应：丢弃
    selectedOutcome.value = detail
  } catch (err) {
    if (err instanceof ApiError) error.value = err.message
  }
}

function codeLabel(code: string | null): string {
  if (!code) return '通过'
  return ({
    'window-early': '早于窗口',
    'window-late': '晚于窗口',
    'location-unreachable': '地点不可达',
    meeting: '会面不同刻',
    'meeting-unreachable': '会面场景缺失',
    'message-order': '消息时序倒置',
    'message-unreachable': '消息跨支线缺失',
  } as Record<string, string>)[code] ?? code
}

function eventGlyph(kind: string): string {
  return ({ arrival: '到', departure: '离', meeting: '★会面', send: '✉发送', read: '✓阅读',
    'attempted-edge': '✕跨越' } as Record<string, string>)[kind] ?? kind
}

const currentFirst = computed(() => proof.value?.first_contradiction ?? null)
</script>

<template>
  <div class="page">
    <header class="topbar">
      <h1>双视角声音漫游 · 故事校样</h1>
      <p class="subtitle">
        逐结局核验整数分钟时间窗口、最短转场、同刻会面与“发送先于阅读”；
        只核验作者结构，不续写台词、不推荐剧情。
      </p>
    </header>

    <section class="samples">
      <span>载入内置故事板：</span>
      <button v-for="(s, key) in samples" :key="key" class="ghost"
        @click="loadSample(key)">{{ s.title }}</button>
    </section>

    <div v-if="error" class="error-banner">⚠ {{ error }}</div>

    <main class="layout">
      <div class="col-editor">
        <StoryboardEditor
          v-if="draft"
          :spec="draft"
          :base-spec="revision?.spec ?? null"
          :blast-scope="activeBlast"
          :disabled="busy"
          @edit="onEdit"
          @commit="commitDraft"
        />

        <section class="revisions">
          <h3>修订链（只追加，旧冻结校样不漂移）</h3>
          <ul>
            <li v-for="r in revisions" :key="r.revision_id"
              :class="{ active: revision?.revision_id === r.revision_id }">
              <button class="link" @click="openRevision(r.revision_id)">
                #{{ r.revision_id }} {{ r.title || r.edit_note }}
              </button>
              <code>{{ r.spec_hash }}</code>
              <span class="time">{{ new Date(r.created_at).toLocaleString() }}</span>
            </li>
          </ul>
          <p v-if="!revisions.length" class="muted">尚无修订——提交故事板即建立第一版冻结校样。</p>
        </section>
      </div>

      <div class="col-proof" v-if="proof">
        <section class="status-card">
          <div class="status" :class="proof.status">
            {{ proof.status === 'valid' ? '✓ 校样通过' : '✕ 发现首个矛盾' }}
          </div>
          <div class="counts">
            <span>A 路线 <b>{{ proof.counts.routes_a }}</b></span>
            <span>B 路线 <b>{{ proof.counts.routes_b }}</b></span>
            <span>结局 <b>{{ proof.counts.outcomes }}</b></span>
            <span class="pass">通过 <b>{{ proof.counts.passed }}</b></span>
            <span class="fail">矛盾 <b>{{ proof.counts.failed }}</b></span>
            <span v-if="proof.counts.cut_a + proof.counts.cut_b > 0" class="cut">
              中断 A{{ proof.counts.cut_a }}/B{{ proof.counts.cut_b }}
            </span>
          </div>
          <p class="hash">结构哈希 sha256:{{ proof.spec_hash }}<span v-if="previewProof"> · 当前为未提交预演</span></p>
        </section>

        <section v-if="currentFirst" class="first-card">
          <h3>首个矛盾（可复述）</h3>
          <p class="detail">{{ currentFirst.detail }}</p>
          <ul class="meta-list">
            <li>类型：<b>{{ codeLabel(currentFirst.code) }}</b></li>
            <li>故事时间：<b>{{ currentFirst.story_time }}′</b></li>
            <li v-if="currentFirst.diff_minutes !== null">相差：<b>{{ currentFirst.diff_minutes }} 分钟</b></li>
            <li>已走边数：A {{ currentFirst.edges_a }} · B {{ currentFirst.edges_b }}</li>
            <li>结局编号：#{{ currentFirst.outcome_index }}</li>
          </ul>
          <div class="events">
            <h4>相关事件</h4>
            <div v-for="(ev, i) in currentFirst.events" :key="i" class="event">
              <span class="glyph">{{ eventGlyph(ev.kind) }}</span>
              <span class="t">{{ ev.time === null ? '时间不成立' : `第 ${ev.time}′` }}</span>
              <span class="who" v-if="ev.role">{{ ev.role.toUpperCase() }}</span>
              <span class="where" v-if="ev.scene">{{ ev.label || ev.scene }}（{{ ev.location }}）</span>
            </div>
          </div>
          <div class="retell">
            <h4>两条路线</h4>
            <RoutePair :route-a="currentFirst.retell.a" :route-b="currentFirst.retell.b" />
          </div>
          <button class="ghost" @click="selectOutcome(currentFirst.outcome_index)">
            打开结局 #{{ currentFirst.outcome_index }} 的完整时间带
          </button>
        </section>

        <section class="outcomes-card">
          <h3>结局矩阵（点击任一结局）</h3>
          <OutcomeGrid :proof="proof" :selected="selectedIndex" @select="selectOutcome" />
        </section>

        <section v-if="selectedOutcome" class="detail-card">
          <h3>结局 #{{ selectedOutcome.i }} 的完整事件时间带</h3>
          <TimelineCanvas
            :route-a="selectedOutcome.route_a"
            :route-b="selectedOutcome.route_b"
            :events="selectedOutcome.events"
          />
          <RoutePair :route-a="selectedOutcome.route_a" :route-b="selectedOutcome.route_b" />
          <div v-if="selectedOutcome.first" class="contradiction">
            <b>{{ codeLabel(selectedOutcome.first.code) }}：</b>
            {{ selectedOutcome.first.detail }}
          </div>
          <div v-else class="all-good">该结局全部约束成立。</div>
        </section>
      </div>

      <div v-else class="col-proof placeholder">
        等待故事板校样……
      </div>
    </main>

    <footer>
      离散枚举 · 笛卡尔逐结局配对 · 合流不合并状态 · 修订只追加
    </footer>
  </div>
</template>

<style>
body { margin: 0; background: #f3f4f6; color: #111827;
  font-family: ui-sans-serif, system-ui, -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; }
</style>

<style scoped>
.page { max-width: 1280px; margin: 0 auto; padding: 20px 22px 60px; }
.topbar h1 { margin: 0; font-size: 22px; }
.subtitle { color: #4b5563; font-size: 13px; margin: 6px 0 14px; }
.samples { display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
  font-size: 13px; color: #4b5563; margin-bottom: 12px; }
button.ghost { border: 1px solid #9ca3af; background: #fff; border-radius: 7px;
  padding: 6px 12px; font-size: 13px; cursor: pointer; }
button.ghost:hover { background: #f3f4f6; }
button.link { background: none; border: none; color: #1d4ed8; cursor: pointer;
  font-size: 13px; padding: 0; }
.error-banner { background: #fef2f2; border: 1px solid #fca5a5; color: #991b1b;
  border-radius: 8px; padding: 8px 12px; margin-bottom: 12px; font-size: 13px; }
.layout { display: grid; grid-template-columns: 430px 1fr; gap: 16px; align-items: start; }
@media (max-width: 1080px) { .layout { grid-template-columns: 1fr; } }
.col-editor { display: flex; flex-direction: column; gap: 14px; }
.col-proof { display: flex; flex-direction: column; gap: 14px; }
.placeholder { color: #9ca3af; padding: 40px; text-align: center; }
.status-card, .first-card, .outcomes-card, .detail-card, .revisions {
  background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 14px 16px;
}
.status { font-size: 20px; font-weight: 700; }
.status.valid { color: #15803d; }
.status.contradiction { color: #b91c1c; }
.counts { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 8px; font-size: 13px; color: #374151; }
.counts .pass { color: #15803d; }
.counts .fail { color: #b91c1c; }
.counts .cut { color: #b45309; }
.hash { color: #9ca3af; font-size: 11px; margin: 8px 0 0; font-family: ui-monospace, monospace; }
.detail { font-size: 14px; background: #fef2f2; padding: 8px 10px; border-radius: 7px; }
.meta-list { font-size: 13px; columns: 2; margin: 8px 0; padding-left: 18px; }
.events h4, .retell h4 { margin: 12px 0 6px; font-size: 13px; }
.event { display: flex; gap: 8px; font-size: 13px; padding: 3px 0; align-items: baseline; }
.glyph { font-weight: 700; color: #1d4ed8; min-width: 64px; }
.t { color: #374151; min-width: 60px; }
.who { font-weight: 700; }
.where { color: #4b5563; }
.retell { margin-top: 8px; }
.revisions h3 { margin: 0 0 8px; font-size: 14px; }
.revisions ul { list-style: none; margin: 0; padding: 0; }
.revisions li { display: flex; gap: 8px; align-items: baseline; font-size: 12px;
  padding: 5px 0; border-bottom: 1px dashed #e5e7eb; flex-wrap: wrap; }
.revisions li.active { background: #eff6ff; margin: 0 -8px; padding-left: 8px; border-radius: 6px; }
.revisions code { color: #9ca3af; font-size: 11px; }
.time { color: #9ca3af; margin-left: auto; }
.muted { color: #9ca3af; font-size: 12px; }
.contradiction { background: #fef2f2; border-radius: 7px; padding: 8px 10px;
  margin-top: 10px; font-size: 13px; }
.all-good { color: #15803d; font-weight: 600; margin-top: 10px; font-size: 13px; }
footer { margin-top: 26px; color: #9ca3af; font-size: 12px; text-align: center; }
</style>
