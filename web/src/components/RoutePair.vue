<script setup lang="ts">
import type { RouteView } from '../types'
import TimelineCanvas from './TimelineCanvas.vue'

defineProps<{
  routeA: RouteView
  routeB: RouteView
}>()

function faultBadge(code: string): string {
  return ({
    'location-unreachable': '地点不可达',
    'window-early': '早于窗口',
    'window-late': '晚于窗口',
  } as Record<string, string>)[code] ?? code
}
</script>

<template>
  <section class="route-cards">
    <article v-for="route in [routeA, routeB]" :key="route.role" class="route-card"
      :class="`role-${route.role}`">
      <header>
        <h3>{{ route.role === 'a' ? '角色 A' : '角色 B' }}</h3>
        <span class="meta">{{ route.steps.length }} 个场景 · {{ route.edges }} 条边 ·
          路线号 <code>{{ route.route_id }}</code></span>
        <span v-if="route.fault" class="fault">✕ {{ faultBadge(route.fault.code) }}</span>
        <span v-else-if="!route.ended" class="fault">中断</span>
      </header>

      <ol class="steps">
        <li v-for="(step, idx) in route.steps" :key="idx" class="step">
          <div class="step-head">
            <span class="scene-label">{{ step.label || step.scene }}</span>
            <span class="loc">@{{ step.location }}</span>
          </div>
          <div class="step-time">
            第 {{ step.arrival }}′ 到 · 停 {{ step.duration }}′ · 第 {{ step.departure }}′ 离
          </div>
          <div v-if="step.edge_label" class="edge">
            —{{ step.edge_label }}→
          </div>
        </li>
      </ol>
    </article>

    <div class="timeline-wrap">
      <h4>分钟时间带（整数离散时刻；灰带是两条路线之间不存在的时刻空洞）</h4>
      <TimelineCanvas :route-a="routeA" :route-b="routeB" />
    </div>
  </section>
</template>

<style scoped>
.route-cards { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.route-card {
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 12px 14px;
  background: #fff;
}
.route-card.role-a { border-top: 3px solid #d97706; }
.route-card.role-b { border-top: 3px solid #1d4ed8; }
header h3 { margin: 0 0 2px; font-size: 15px; }
.meta { color: #6b7280; font-size: 12px; }
.fault { color: #dc2626; font-size: 12px; font-weight: 600; margin-left: 8px; }
.steps { list-style: none; margin: 10px 0 0; padding: 0; }
.step { padding: 8px 0; border-bottom: 1px dashed #e5e7eb; font-size: 13px; }
.step:last-child { border-bottom: none; }
.step-head { display: flex; justify-content: space-between; gap: 8px; }
.scene-label { font-weight: 600; }
.loc { color: #6b7280; font-size: 12px; }
.step-time { color: #374151; margin-top: 2px; }
.edge { color: #0f766e; font-size: 12px; margin-top: 2px; }
.timeline-wrap {
  grid-column: 1 / -1;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 10px 12px;
  background: #fafafa;
}
.timeline-wrap h4 { margin: 2px 0 6px; font-size: 13px; color: #374151; }
@media (max-width: 820px) { .route-cards { grid-template-columns: 1fr; } }
</style>
