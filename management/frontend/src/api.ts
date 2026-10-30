import { onBeforeUnmount, ref, shallowRef, watch } from 'vue'

export class ApiError extends Error {
  constructor(readonly status: number, message: string) { super(message) }
}

export async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response
  try { response = await fetch(`/api/v1${path}`, { signal, cache: 'no-store' }) }
  catch (cause) {
    if (signal?.aborted) throw cause
    throw new ApiError(0, '无法连接查询服务，请稍后重试。')
  }
  if (!response.headers.get('content-type')?.includes('application/json')) throw new ApiError(response.status, '查询服务暂时不可用，请稍后重试。')
  const payload = await response.json()
  if (!response.ok) throw new ApiError(response.status, payload.error?.message ?? '查询失败，请稍后重试。')
  return payload
}

export function query(values: Record<string, string | number | undefined>): string {
  const params = new URLSearchParams()
  Object.entries(values).forEach(([key, value]) => { if (value !== undefined && value !== '') params.set(key, String(value)) })
  return params.size ? `?${params}` : ''
}

export function useLoad<T>(key: () => unknown, loader: (signal: AbortSignal) => Promise<T>) {
  const data = shallowRef<T>()
  const loading = ref(false)
  const error = ref('')
  let controller: AbortController | undefined
  async function reload() {
    controller?.abort()
    const current = new AbortController()
    controller = current
    loading.value = true; error.value = ''; data.value = undefined
    try {
      const value = await loader(current.signal)
      if (!current.signal.aborted) data.value = value
    } catch (cause) {
      if (!current.signal.aborted) error.value = cause instanceof Error ? cause.message : '查询失败。'
    } finally {
      if (controller === current) loading.value = false
    }
  }
  watch(key, reload, { immediate: true })
  onBeforeUnmount(() => controller?.abort())
  return { data, loading, error, reload }
}
