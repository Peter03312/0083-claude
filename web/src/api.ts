// API 客户端。
//
// 防“异步旧响应贴到新修订”：
// 每次请求带调用方持有的 revisionId，响应回来后若前端已经切到更新的修订，
// 调用方通过 assertCurrent 丢弃过期结果；服务端则用 parent_id 做最终防线。

import type {
  BlastScope,
  OutcomeDetail,
  Proof,
  Revision,
  StoryboardSpec,
} from './types'

const BASE = '/api'

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  const body = await resp.json().catch(() => ({}))
  if (!resp.ok) {
    throw new ApiError(resp.status, body.error ?? 'http', body.message ?? resp.statusText)
  }
  return body as T
}

export const api = {
  health(): Promise<{ ok: boolean }> {
    return request('/health')
  },

  samples(): Promise<Record<string, { title: string; spec: StoryboardSpec }>> {
    return request('/samples')
  },

  revisions(): Promise<{ revisions: { revision_id: number; created_at: string; title: string; spec_hash: string; edit_note: string }[] }> {
    return request('/revisions')
  },

  latest(): Promise<Revision> {
    return request('/revisions/latest')
  },

  revision(id: number): Promise<Revision> {
    return request(`/revisions/${id}`)
  },

  commit(spec: StoryboardSpec, parentId: number | null, note: string): Promise<Revision> {
    return request('/revisions', {
      method: 'POST',
      body: JSON.stringify({ spec, parent_id: parentId, note }),
    })
  },

  preview(spec: StoryboardSpec): Promise<Proof> {
    return request('/prove', { method: 'POST', body: JSON.stringify({ spec }) })
  },

  outcome(revisionId: number, index: number): Promise<OutcomeDetail> {
    return request(`/revisions/${revisionId}/outcomes/${index}`)
  },

  blastPreview(revisionId: number, spec: StoryboardSpec): Promise<BlastScope> {
    return request(`/revisions/${revisionId}/blast-preview`, {
      method: 'POST',
      body: JSON.stringify({ spec }),
    })
  },
}
