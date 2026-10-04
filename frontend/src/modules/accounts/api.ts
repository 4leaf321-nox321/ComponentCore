import { api } from '@/shared/api/client'
import type { Account, TemporaryPassword } from '@/shared/api/types'

export const accountsApi = {
  list: () => api.get<Account[]>('/accounts?limit=100'),
  /**
   * **모든 계정** — 서버는 한 번에 100명까지라(쪽 수를 안 준다) 모자라지 않을 때까지 잇는다. 고르개 ·
   * 계정 화면이 100명에서 잘리지 않게(2026-10-04 점검).
   */
  all: async (): Promise<Account[]> => {
    const out: Account[] = []
    for (let offset = 0; ; offset += 100) {
      const page = await api.get<Account[]>(`/accounts?limit=100&offset=${offset}`)
      out.push(...page)
      if (page.length < 100) return out
    }
  },
  create: (body: { email: string; display_name: string; is_system_admin: boolean }) =>
    api.post<TemporaryPassword>('/accounts', body),
  suspend: (id: string) => api.post<Account>(`/accounts/${id}/suspend`),
  activate: (id: string) => api.post<Account>(`/accounts/${id}/activate`),
  setSystemAdmin: (id: string, grant: boolean) =>
    api.post<Account>(`/accounts/${id}/system-admin`, { is_system_admin: grant }),
  resetPassword: (id: string) => api.post<TemporaryPassword>(`/accounts/${id}/reset-password`),
  remove: (id: string) => api.delete<Account>(`/accounts/${id}`),
}
