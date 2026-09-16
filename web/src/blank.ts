import type { StoryboardSpec } from './types'

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
