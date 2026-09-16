// 与后端 JSON 对应的类型定义。

export interface SceneSpec {
  id: string
  label?: string
  location: string
  durations: number[]
  choices: { to: string; label?: string }[]
}

export interface WindowSpec {
  scene: string
  open: number
  close: number
}

export interface TransitionSpec {
  from: string
  to: string
  minutes: number
}

export interface MeetingSpec {
  kind: 'meeting'
  scene_a: string
  scene_b: string
  label?: string
}

export interface MessageSpec {
  kind: 'message'
  send_role: Role
  send_scene: string
  read_role: Role
  read_scene: string
  label?: string
}

export interface StoryboardSpec {
  title?: string
  start: string
  scenes: SceneSpec[]
  windows?: WindowSpec[]
  transitions?: TransitionSpec[]
  meetings?: MeetingSpec[]
  messages?: MessageSpec[]
}

export type Role = 'a' | 'b'

export interface RouteStep {
  seq: number
  scene: string
  label: string
  location: string
  arrival: number
  duration: number
  departure: number
  edge_ord: number | null
  edge_label: string | null
  duration_ord: number
  window: { open: number; close: number; state: 'in-window' | 'window-early' | 'window-late' } | null
}

export interface RouteFault {
  code: string
  detail: string
  arrival: number
  edge_ord: number | null
}

export interface RouteView {
  role: Role
  route_id: string
  ended: boolean
  edges: number
  fault: RouteFault | null
  steps: RouteStep[]
}

export interface OutcomeCompact {
  i: number
  ra: string
  rb: string
  ta: number
  tb: number
  ended_a: boolean
  ended_b: boolean
  ok: boolean
  code: string | null
  story_time: number | null
}

export interface ProofEvent {
  kind: 'arrival' | 'departure' | 'meeting' | 'send' | 'read' | 'attempted-edge'
  time: number | null
  role: string | null
  scene: string | null
  location: string | null
  label: string
  ref: number | null
}

export interface FirstContradiction {
  code: string
  detail: string
  story_time: number | null
  diff_minutes: number | null
  role: string | null
  edge_ord: number | null
  edges_a: number
  edges_b: number
  outcome_index: number
  events: ProofEvent[]
  retell: { a: RouteView; b: RouteView }
}

export interface Proof {
  spec_hash: string
  status: 'valid' | 'contradiction'
  counts: {
    routes_a: number
    routes_b: number
    outcomes: number
    passed: number
    failed: number
    cut_a: number
    cut_b: number
  }
  routes: { a: RouteView[]; b: RouteView[] }
  outcomes: OutcomeCompact[]
  first_contradiction: FirstContradiction | null
}

export interface BlastScope {
  total: number
  recompute_count: number
  recompute_indices: number[]
  dirty_scenes: string[]
  seed_scenes: string[]
  reasons: Record<string, string[]>
  structural: boolean
  constraints_changed: boolean
}

export interface Revision {
  revision_id: number
  created_at: string
  title: string
  spec_hash: string
  spec: StoryboardSpec
  proof: Proof
  edit_note: string
  changes_from_parent: BlastScope | null
}

export interface OutcomeDetail {
  i: number
  route_a: RouteView
  route_b: RouteView
  events: ProofEvent[]
  contradictions: FirstContradiction[]
  first: FirstContradiction | null
}
