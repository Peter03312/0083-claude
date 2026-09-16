<script setup lang="ts">
import { computed } from 'vue'
import type { Proof } from '../types'

const props = defineProps<{
  proof: Proof
  selected: number | null
}>()

const emit = defineEmits<{ (e: 'select', index: number): void }>()

const cols = computed(() => props.proof.routes.b)
const rows = computed(() => props.proof.routes.a)

function cell(ia: number, ib: number) {
  return props.proof.outcomes[ia * props.proof.routes.b.length + ib]
}

function title(code: string | null): string {
  if (!code) return '该结局通过：窗口/转场/会面/消息全部成立'
  return ({
    'window-early': '早于时间窗口',
    'window-late': '晚于时间窗口',
    'location-unreachable': '缺少最短转场，地点不可达',
    meeting: '会面未同刻',
    'meeting-unreachable': '会面场景不在该结局的路线上',
    'message-order': '阅读不晚于发送',
    'message-unreachable': '消息发送/阅读场景跨支线缺失',
  } as Record<string, string>)[code] ?? code
}
</script>

<template>
  <div class="grid-wrap">
    <table class="outcome-grid">
      <thead>
        <tr>
          <th></th>
          <th v-for="rb in cols" :key="rb.route_id" :title="rb.route_id">
            B: {{ rb.steps.map((s) => s.label || s.scene).join(' → ') }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(ra, ia) in rows" :key="ra.route_id">
          <th class="rowhead" :title="ra.route_id">
            A: {{ ra.steps.map((s) => s.label || s.scene).join(' → ') }}
          </th>
          <td v-for="(rb, ib) in cols" :key="rb.route_id">
            <button
              class="cell"
              :class="{
                ok: cell(ia, ib).ok,
                bad: !cell(ia, ib).ok,
                cut: !cell(ia, ib).ended_a || !cell(ia, ib).ended_b,
                active: selected === cell(ia, ib).i,
              }"
              :title="title(cell(ia, ib).code)"
              @click="emit('select', cell(ia, ib).i)"
            >
              <span class="i">#{{ cell(ia, ib).i }}</span>
              <span class="times">{{ cell(ia, ib).ta }}′/{{ cell(ia, ib).tb }}′</span>
            </button>
          </td>
        </tr>
      </tbody>
    </table>
    <p class="legend">
      <i class="sw ok"></i> 通过
      <i class="sw bad"></i> 矛盾
      <i class="sw cut"></i> 路线中断（缺最短转场）
      ；每格两位数字是 A/B 到达终点的离散分钟。
    </p>
  </div>
</template>

<style scoped>
.grid-wrap { overflow-x: auto; }
.outcome-grid { border-collapse: separate; border-spacing: 4px; font-size: 12px; }
th { font-weight: 500; color: #374151; text-align: left; padding: 4px 6px;
  max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rowhead { max-width: 220px; }
.cell {
  width: 74px; height: 46px; border-radius: 8px; border: 1px solid transparent;
  cursor: pointer; display: flex; flex-direction: column; align-items: center;
  justify-content: center; font-size: 11px; gap: 2px;
}
.cell.ok { background: #dcfce7; border-color: #86efac; color: #166534; }
.cell.bad { background: #fee2e2; border-color: #fca5a5; color: #991b1b; }
.cell.cut { outline: 2px dashed #f59e0b; outline-offset: -2px; }
.cell.active { box-shadow: 0 0 0 3px rgba(29, 78, 216, 0.35); }
.i { font-weight: 700; }
.legend { color: #6b7280; font-size: 12px; margin: 8px 2px; }
.sw { display: inline-block; width: 12px; height: 12px; border-radius: 3px;
  margin: 0 4px 0 12px; vertical-align: -1px; }
.sw.ok { background: #dcfce7; border: 1px solid #86efac; }
.sw.bad { background: #fee2e2; border: 1px solid #fca5a5; }
.sw.cut { background: #fef3c7; border: 1px dashed #f59e0b; }
</style>
