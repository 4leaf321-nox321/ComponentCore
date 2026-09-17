import { api } from '@/shared/api/client'
import type { Account, TemporaryPassword } from '@/shared/api/types'

export const accountsApi = {
  list: () => api.get<Account[]>('/accounts?limit=100'),
  create: (body: { email: string; display_name: string; is_system_admin: boolean }) =>
    api.post<TemporaryPassword>('/accounts', body),
  suspend: (id: string) => api.post<Account>(`/accounts/${id}/suspend`),
  activate: (id: string) => api.post<Account>(`/accounts/${id}/activate`),
  setSystemAdmin: (id: string, grant: boolean) =>
    api.post<Account>(`/accounts/${id}/system-admin`, { is_system_admin: grant }),
  resetPassword: (id: string) => api.post<TemporaryPassword>(`/accounts/${id}/reset-password`),
  remove: (id: string) => api.delete<Account>(`/accounts/${id}`),
}
