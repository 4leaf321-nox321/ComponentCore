import { api, postForBlob } from '@/shared/api/client'

export interface PrimitiveKinds {
  kinds: string[]
  examples: Record<string, Record<string, unknown>>
}

export interface PrimitiveInfo {
  kind: string
  bbox_size: [number, number, number]
  volume: number
  face_count: number
}

export const cadApi = {
  kinds: () => api.get<PrimitiveKinds>('/cad/primitives'),
  info: (spec: Record<string, unknown>) => api.post<PrimitiveInfo>('/cad/primitives/info', { spec }),
  glb: (spec: Record<string, unknown>) => postForBlob('/cad/primitives/glb', { spec }),
  step: (spec: Record<string, unknown>) => postForBlob('/cad/primitives/step', { spec }),
}
