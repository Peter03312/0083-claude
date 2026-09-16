<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { BlastScope, StoryboardSpec } from '../types'

const props = defineProps<{
  spec: StoryboardSpec          // 当前工作草稿
  baseSpec: StoryboardSpec | null  // 已冻结修订（用于判断草稿是否有待提交改动）
  blastScope: BlastScope | null
  disabled?: boolean
}>()

const emit = defineEmits<{
  (e: 'edit', spec: StoryboardSpec): void
  (e: 'commit', spec: StoryboardSpec, note: string): void
}>()

// 本地工作副本：编辑器里的改动先在草稿上出现，提交才形成新修订。
const text = ref('')
const note = ref('')
const error = ref('')

watch(() => props.spec, (spec) => {
  text.value = JSON.stringify(spec, null, 2)
  error.value = ''
}, { immediate: true, deep: true })

const parsed = computed<StoryboardSpec | null>(() => {
  try {
    return JSON.parse(text.value) as StoryboardSpec
  } catch {
    return null
  }
})

const dirty = computed(() => {
  if (!parsed.value || !props.baseSpec) return Boolean(parsed.value)
  return JSON.stringify(parsed.value) !== JSON.stringify(props.baseSpec)
})

// 结构化字段快捷编辑（时长/窗口/转场）。
function setDuration(sceneId: string, values: number[]) {
  const spec = cloneSpec()
  const scene = spec.scenes.find((s) => s.id === sceneId)
  if (scene) scene.durations = values
  apply(spec)
}

function setWindow(sceneId: string, patch: Partial<{ open: number; close: number }>) {
  const spec = cloneSpec()
  spec.windows ??= []
  let w = spec.windows.find((x) => x.scene === sceneId)
  if (!w) {
    w = { scene: sceneId, open: 0, close: 0 }
    spec.windows.push(w)
  }
  Object.assign(w, patch)
  apply(spec)
}

function setTransition(idx: number, minutes: number) {
  const spec = cloneSpec()
  if (spec.transitions && spec.transitions[idx] !== undefined) {
    spec.transitions[idx].minutes = minutes
    apply(spec)
  }
}

function cloneSpec(): StoryboardSpec {
  return JSON.parse(text.value || '{}') as StoryboardSpec
}

function apply(spec: StoryboardSpec) {
  text.value = JSON.stringify(spec, null, 2)
  error.value = ''
  emit('edit', spec)
}

function onText() {
  if (parsed.value) {
    error.value = ''
    emit('edit', parsed.value)
  } else {
    error.value = 'JSON 解析失败：还不能提交校样'
  }
}

function commit() {
  if (!parsed.value) {
    error.value = 'JSON 解析失败：还不能提交校样'
    return
  }
  emit('commit', parsed.value, note.value || '作者编辑')
  note.value = ''
}

function dirtyScene(id: string): boolean {
  return props.blastScope?.dirty_scenes.includes(id) ?? false
}
</script>

<template>
  <section class="editor">
    <div class="quick-edit" v-if="parsed">
      <h4>快捷编辑（直接建立新修订所需的三类改动）</h4>
      <div class="edit-block">
        <strong>场景时长（1~3 个整数分钟）</strong>
        <div v-for="scene in parsed.scenes ?? []" :key="scene.id" class="row"
          :class="{ dirty: dirtyScene(scene.id) }">
          <span class="name">{{ scene.label || scene.id }}
            <em v-if="dirtyScene(scene.id)">影响域内</em>
          </span>
          <input
            :value="scene.durations.join(', ')"
            :disabled="disabled"
            @change="setDuration(scene.id, String(($event.target as HTMLInputElement).value)
              .split(',').map((x) => parseInt(x.trim(), 10)).filter((x) => !Number.isNaN(x)))"
          />
        </div>
      </div>

      <div class="edit-block">
        <strong>绝对时间窗口</strong>
        <div v-for="w of parsed.windows ?? []" :key="w.scene" class="row"
          :class="{ dirty: dirtyScene(w.scene) }">
          <span class="name">{{ w.scene }}</span>
          <label>开 <input type="number" class="num" :value="w.open" :disabled="disabled"
            @change="setWindow(w.scene, { open: Number(($event.target as HTMLInputElement).value) })" /></label>
          <label>关 <input type="number" class="num" :value="w.close" :disabled="disabled"
            @change="setWindow(w.scene, { close: Number(($event.target as HTMLInputElement).value) })" /></label>
        </div>
      </div>

      <div class="edit-block">
        <strong>地点间最短转场（分钟）</strong>
        <div v-for="(t, idx) in parsed.transitions ?? []" :key="idx" class="row">
          <span class="name">{{ t.from }} ↔ {{ t.to }}</span>
          <input type="number" class="num" :value="t.minutes" :disabled="disabled"
            @change="setTransition(idx, Number(($event.target as HTMLInputElement).value))" />
        </div>
      </div>

      <details class="raw">
        <summary>原始故事板 JSON</summary>
        <textarea :value="text" :disabled="disabled" @input="onText" rows="14" spellcheck="false"></textarea>
      </details>

      <p v-if="error" class="error">{{ error }}</p>
      <div class="commit-row">
        <input v-model="note" class="note" placeholder="本次编辑说明（可选）" :disabled="disabled" />
        <button class="primary" :disabled="disabled || !dirty || !!error" @click="commit">
          提交为新修订（冻结校样）
        </button>
        <span v-if="dirty" class="hint">有未提交改动 · 影响域会随提交写入修订链</span>
      </div>

      <div v-if="blastScope && dirty" class="blast">
        <h5>图依赖影响域（基于当前修订预演）</h5>
        <p>
          必须重算结局
          <b>{{ blastScope.recompute_count }}/{{ blastScope.total }}</b>
          <template v-if="blastScope.structural">· 结构变化，全量重算</template>
          <template v-else-if="blastScope.constraints_changed">· 会面/消息变化，全量重裁约束</template>
        </p>
        <p v-if="blastScope.dirty_scenes.length" class="scenes">
          受影响场景：{{ blastScope.dirty_scenes.join('、') }}
        </p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.editor { background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 14px; }
h4 { margin: 0 0 10px; }
.edit-block { margin-bottom: 12px; }
.edit-block strong { font-size: 13px; color: #374151; }
.row { display: flex; align-items: center; gap: 8px; margin: 5px 0;
  padding: 3px 6px; border-radius: 6px; font-size: 13px; }
.row.dirty { background: #fff7ed; }
.name { min-width: 180px; color: #111827; }
.name em { color: #c2410c; font-style: normal; font-size: 11px; margin-left: 6px; }
input[type='text'], input:not([type]), .note { padding: 4px 8px; border: 1px solid #d1d5db;
  border-radius: 6px; font-size: 13px; }
.num { width: 64px; padding: 3px 6px; border: 1px solid #d1d5db; border-radius: 6px; }
.raw textarea { width: 100%; font-family: ui-monospace, monospace; font-size: 12px;
  border: 1px solid #d1d5db; border-radius: 6px; padding: 8px; box-sizing: border-box; }
.commit-row { display: flex; gap: 10px; align-items: center; margin-top: 10px; flex-wrap: wrap; }
.note { flex: 1; min-width: 180px; }
.primary { background: #1d4ed8; color: #fff; border: none; border-radius: 7px;
  padding: 8px 16px; font-weight: 600; cursor: pointer; }
.primary:disabled { background: #9ca3af; cursor: not-allowed; }
.hint { color: #b45309; font-size: 12px; }
.error { color: #dc2626; font-size: 13px; }
.blast { margin-top: 12px; background: #f8fafc; border: 1px dashed #94a3b8;
  border-radius: 8px; padding: 8px 12px; font-size: 13px; }
.blast h5 { margin: 2px 0 6px; }
.scenes { color: #9a3412; }
</style>
