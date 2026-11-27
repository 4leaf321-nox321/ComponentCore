/**
 * **재료 모델 — 소성**(② 비선형 정적, SimEngBay 와 정함 2026-11-27). 모델 트리의 물성 항목 안에 선다.
 *
 * - 손으로 적는다: 이선형(항복응력 · 접선계수)과 다선형(진응력 대 진소성변형률 표, 첫 행은 소성 변형률 0). MatNexus 의 물성
 *   카드에서 곡선을 받는 길은 카드의 방향 · 판이 정해진 뒤에 연다.
 * - 값은 입력 단위계(응력 MPa)로 적는다 — 내보낼 때 서버가 내보내기 계로 옮긴다.
 * - **해석 케이스에서만** 쓴다(받는 쪽이 v2 로만 받는다). 케이스가 없는 조건이면 고르지 못하게 하고 그렇다고 말한다.
 * - 점검은 서버가 저장할 때 한다(`materials.check_plastic` — 0 < σy, 0 ≤ Et, 표의 변형률은 늘고 응력은 줄지 않는다).
 */

import type { MaterialItem } from '@/modules/conditions/api'
import { FrequencyTable } from '@/modules/conditions/FrequencyTable'
import { NumberText } from '@/modules/conditions/NumberText'

/** 서버 `materials.MATERIAL_MODELS` 와 같은 낱말 · 차례. */
const MODELS: [string, string][] = [
  ['linear_elastic', '선형 탄성'],
  ['bilinear_isotropic', '이선형 소성(등방 경화)'],
  ['multilinear_isotropic', '다선형 소성(등방 경화)'],
]

interface Plastic {
  yield_stress?: number | string | null
  tangent_modulus?: number | string | null
  table?: (number | string)[][] | null
}

/** `12` → 12, `=식` → 그대로, 빈칸 → null. */
function valueOf(text: string): number | string | null {
  const trimmed = text.trim()
  if (trimmed === '') return null
  if (trimmed.startsWith('=')) return trimmed
  const num = Number(trimmed)
  return Number.isFinite(num) ? num : trimmed
}

export function PlasticEditor({
  material,
  enabled,
  stressUnit = 'MPa',
  onChange,
}: {
  material: MaterialItem
  /** 해석 케이스가 있는가 — 없으면 선형 탄성만. */
  enabled: boolean
  /** 입력 단위계의 응력 단위. */
  stressUnit?: string
  onChange: (patch: Partial<MaterialItem>) => void
}) {
  const model = String(material.model ?? 'linear_elastic')
  const plastic = (material.plastic ?? {}) as Plastic
  const set = (patch: Partial<Plastic>) => onChange({ plastic: { ...plastic, ...patch } })

  return (
    <div className="space-y-1.5" aria-label="재료 모델">
      <label className="flex items-center gap-1.5">
        <span className="text-muted-foreground">재료 모델</span>
        <select
          aria-label="재료 모델"
          className="bg-background rounded border px-1.5 py-0.5"
          value={model}
          disabled={!enabled && model === 'linear_elastic'}
          onChange={(e) => onChange(e.target.value === 'linear_elastic' ? { model: e.target.value, plastic: null } : { model: e.target.value, plastic: {} })}
        >
          {MODELS.map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
      </label>
      {!enabled && model === 'linear_elastic' && (
        <p className="text-muted-foreground">소성은 해석 케이스에서 지정합니다. 정적 해석 설정의 ‘해석 케이스로 나누기’를 사용하십시오.</p>
      )}
      {model === 'bilinear_isotropic' && (
        <div className="flex flex-wrap gap-3">
          <label className="space-y-0.5">
            <span className="text-muted-foreground block">항복응력({stressUnit})</span>
            <NumberText aria-label="항복응력" className="h-7 w-24 px-1.5 text-xs" value={plastic.yield_stress} onText={(text) => set({ yield_stress: valueOf(text) })} />
          </label>
          <label className="space-y-0.5">
            <span className="text-muted-foreground block">접선계수({stressUnit})</span>
            <NumberText aria-label="접선계수" className="h-7 w-24 px-1.5 text-xs" value={plastic.tangent_modulus} onText={(text) => set({ tangent_modulus: valueOf(text) })} />
          </label>
        </div>
      )}
      {model === 'multilinear_isotropic' && (
        <FrequencyTable
          title="진응력 대 진소성변형률"
          columns={[{ title: '진소성변형률' }, { title: '진응력', unit: stressUnit }]}
          description="첫 행의 소성 변형률은 0이고 그 응력이 항복응력입니다. 소성 변형률은 커지고 응력은 줄지 않아야 합니다."
          plot="linear"
          value={plastic.table}
          onChange={(rows) => set({ table: rows })}
        />
      )}
      {model !== 'linear_elastic' && (
        <p className="text-muted-foreground">
          von Mises 등방 경화로 풉니다. 정적 해석에서만 쓰며 모달, 랜덤 진동은 탄성 값으로 풉니다. 표의 마지막 점 뒤의 동작은 해석 쪽 판정을
          따릅니다. 해석 쪽(SimEngBay)이 받는 판부터 DOE로 내보낼 수 있습니다.
        </p>
      )}
    </div>
  )
}
