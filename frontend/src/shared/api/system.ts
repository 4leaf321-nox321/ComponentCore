import { api } from '@/shared/api/client'

export interface Health {
  status: string
  version: string
  app: string
}

export const UNKNOWN_VERSION = 'unknown'

export const systemApi = {
  health: () => api.get<Health>('/health'),
}
