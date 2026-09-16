<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { ProofEvent, RouteView } from '../types'

const props = defineProps<{
  routeA: RouteView
  routeB: RouteView
  events?: ProofEvent[]
  highlightOutcome?: number
}>()

const canvas = ref<HTMLCanvasElement | null>(null)
let observer: ResizeObserver | null = null

const ROLE_COLORS = { a: '#d97706', b: '#1d4ed8' } as const

// 时间带范围：两条路线上出现过的离散时刻。
const timeRange = computed(() => {
  const times: number[] = []
  for (const r of [props.routeA, props.routeB]) {
    for (const s of r.steps) {
      times.push(s.arrival, s.departure)
    }
  }
  const events = props.events ?? []
  for (const ev of events) if (ev.time !== null) times.push(ev.time)
  const min = Math.min(...times)
  const max = Math.max(...times)
  return { min, max }
})

// 离散空洞：相邻可达时刻之间大于 1 的部分（“中间根本不存在的时刻”）。
const holes = computed(() => {
  const ticks = new Set<number>()
  for (const r of [props.routeA, props.routeB]) {
    for (const s of r.steps) ticks.add(s.arrival)
  }
  const sorted = [...ticks].sort((x, y) => x - y)
  const gaps: { from: number; to: number }[] = []
  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i] - sorted[i - 1] > 1) gaps.push({ from: sorted[i - 1], to: sorted[i] })
  }
  return gaps
})

function draw() {
  const cv = canvas.value
  if (!cv) return
  const dpr = window.devicePixelRatio || 1
  const width = cv.clientWidth
  const height = cv.clientHeight
  cv.width = width * dpr
  cv.height = height * dpr
  const ctx = cv.getContext('2d')!
  ctx.scale(dpr, dpr)
  ctx.clearRect(0, 0, width, height)

  const padL = 96
  const padR = 24
  const padT = 28
  const padB = 44
  const bandW = Math.max(80, width - padL - padR)
  const { min, max } = timeRange.value
  const span = Math.max(1, max - min)
  const x = (t: number) => padL + ((t - min) / span) * bandW

  // ---- 背景：网格与分钟刻度 ----
  ctx.strokeStyle = '#e5e7eb'
  ctx.fillStyle = '#6b7280'
  ctx.font = '11px ui-sans-serif, system-ui'
  ctx.textAlign = 'center'
  for (let t = min; t <= max; t++) {
    const xx = x(t)
    ctx.beginPath()
    ctx.moveTo(xx, padT - 6)
    ctx.lineTo(xx, height - padB + 8)
    ctx.stroke()
    ctx.fillText(`${t}`, xx, height - padB + 24)
  }
  ctx.fillText('分钟 →', padL + bandW + 4, height - padB + 24)

  // ---- 离散空洞（可达时刻之间的不存在区间） ----
  ctx.fillStyle = 'rgba(107,114,128,0.12)'
  for (const g of holes.value) {
    ctx.fillRect(x(g.from) + 3, padT - 6, x(g.to) - x(g.from) - 6,
      height - padB - padT + 14)
  }

  // ---- 两条角色泳道 ----
  const laneH = 54
  const laneY: Record<string, number> = { a: padT + 14, b: padT + 14 + laneH + 26 }

  function drawRoute(route: RouteView) {
    const color = ROLE_COLORS[route.role]
    const y = laneY[route.role]
    ctx.fillStyle = color
    ctx.font = 'bold 12px ui-sans-serif, system-ui'
    ctx.textAlign = 'right'
    ctx.fillText(route.role === 'a' ? '角色 A' : '角色 B', padL - 10, y + 14)

    // 场景停留条：到达→离开（窗口违规的中途场景标红）
    for (const step of route.steps) {
      const badWindow = step.window && step.window.state !== 'in-window'
      const barColor = badWindow ? '#dc2626' : color
      ctx.fillStyle = barColor + '33'
      ctx.strokeStyle = barColor
      ctx.lineWidth = 1.5
      const x0 = x(step.arrival)
      const x1 = Math.max(x0 + 2, x(step.departure))
      ctx.beginPath()
      ctx.roundRect(x0, y, x1 - x0, 28, 5)
      ctx.fill()
      ctx.stroke()
      ctx.fillStyle = '#111827'
      ctx.font = '11px ui-sans-serif, system-ui'
      ctx.textAlign = 'center'
      const label = step.label || step.scene
      ctx.fillText(truncate(label, Math.max(24, (x1 - x0) / 6)), (x0 + x1) / 2, y + 18)
    }

    // 转场连接（离开 → 下一次到达），无转场断层画红虚线。
    ctx.strokeStyle = color
    for (let i = 1; i < route.steps.length; i++) {
      const prev = route.steps[i - 1]
      const cur = route.steps[i]
      ctx.beginPath()
      ctx.lineWidth = 2
      ctx.moveTo(x(prev.departure), y + 14)
      ctx.lineTo(x(cur.arrival), y + 14)
      ctx.stroke()
    }
    if (route.fault) {
      const last = route.steps[route.steps.length - 1]
      const fx = x(last.departure)
      ctx.strokeStyle = '#dc2626'
      ctx.setLineDash([5, 4])
      ctx.beginPath()
      ctx.moveTo(fx, y + 14)
      ctx.lineTo(Math.min(fx + 34, padL + bandW), y + 14)
      ctx.stroke()
      ctx.setLineDash([])
      ctx.fillStyle = '#dc2626'
      ctx.textAlign = 'left'
      ctx.font = 'bold 11px ui-sans-serif, system-ui'
      ctx.fillText('✕ ' + faultText(route.fault.code), fx + 4, y + 2)
    }
  }

  drawRoute(props.routeA)
  drawRoute(props.routeB)

  // ---- 会面/消息标记（来自结局事件表） ----
  const events = props.events ?? []
  for (const ev of events) {
    if (ev.time === null) continue
    if (ev.kind === 'meeting') {
      drawMarker(x(ev.time), (laneY.a + laneY.b) / 2 + 14, '#059669', '★')
    } else if (ev.kind === 'send') {
      const ry = (ev.role === 'a' ? laneY.a : laneY.b) - 8
      drawMarker(x(ev.time), ry, '#7c3aed', '发')
    } else if (ev.kind === 'read') {
      const ry = (ev.role === 'a' ? laneY.a : laneY.b) + 36
      drawMarker(x(ev.time), ry, '#0891b2', '读')
    }
  }
}

function faultText(code: string): string {
  switch (code) {
    case 'location-unreachable': return '地点不可达'
    case 'window-early': return '早于窗口'
    case 'window-late': return '晚于窗口'
    default: return code
  }
}

function drawMarker(x: number, y: number, color: string, glyph: string) {
  const ctx = canvas.value!.getContext('2d')!
  ctx.fillStyle = color
  ctx.beginPath()
  ctx.arc(x, y, 9, 0, Math.PI * 2)
  ctx.fill()
  ctx.fillStyle = '#fff'
  ctx.font = 'bold 11px ui-sans-serif, system-ui'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(glyph, x, y + 0.5)
  ctx.textBaseline = 'alphabetic'
}

function truncate(text: string, max: number): string {
  return text.length > max ? text.slice(0, max - 1) + '…' : text
}

onMounted(() => {
  observer = new ResizeObserver(draw)
  if (canvas.value) observer.observe(canvas.value)
  draw()
})
onBeforeUnmount(() => observer?.disconnect())
watch(() => [props.routeA, props.routeB, props.events], draw, { deep: true })
</script>

<template>
  <canvas ref="canvas" class="timeline-canvas" aria-label="分钟时间带"></canvas>
</template>

<style scoped>
.timeline-canvas {
  width: 100%;
  height: 220px;
  display: block;
}
</style>
