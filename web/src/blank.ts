import type { StoryboardSpec } from './types'

// 故事板是纯 JSON 数据。用 JSON 克隆而非 structuredClone：
// 后者在旧版浏览器/WebView 中可能不存在，且对 Vue 响应式代理可能抛
// DataCloneError（表现为点击样例后控制台报克隆错误、编辑器无反应）。
export function cloneSpec<T>(spec: T): T {
  return JSON.parse(JSON.stringify(spec)) as T
}

// 服务尚未就绪或库为空时的初始草稿：编辑器立即可见，可直接改出第一版故事板。
export function emptyStoryboard(): StoryboardSpec {
  return {
    title: '未命名声音漫游',
    start: 'gate',
    scenes: [
      {
        id: 'gate',
        label: '起点',
        location: '起点地点',
        durations: [1],
        choices: [
          { to: 'route_a', label: '绕钟楼' },
          { to: 'route_b', label: '穿连廊' },
        ],
      },
      { id: 'route_a', label: '路线甲场景', location: '地点甲', durations: [1], choices: [{ to: 'meet' }] },
      { id: 'route_b', label: '路线乙场景', location: '地点乙', durations: [1], choices: [{ to: 'meet' }] },
      { id: 'meet', label: '会面点', location: '同一声景', durations: [1], choices: [] },
    ],
    windows: [],
    transitions: [],
    meetings: [
      { kind: 'meeting', scene_a: 'meet', scene_b: 'meet', label: '同声会面' },
    ],
    messages: [],
  }
}
