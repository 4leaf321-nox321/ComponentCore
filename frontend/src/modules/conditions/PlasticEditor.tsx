/**
 * **재료 모델 — 소성**(② 비선형 정적, SimEngBay 와 정함 2026-11-27). 모델 트리의 물성 항목 안에 선다.
 *
 * - 손으로 적는다: 이선형(항복응력 · 접선계수)과 다선형(진응력 대 진소성변형률 표, 첫 행은 소성 변형률 0).
 * - **MatNexus 물성 카드에서 받는다**(다선형): 그 재료의 인장 카드를 방향마다 보이고, 사용자가 방향을 골라 받는다(2026-11-27
 *   결정). 확정(published) 카드만 쓴다 — 초안 · 내린 카드는 까닭과 함께 보이되 고르지 못한다. 받은 표를 손으로 고치면 손으로
 *   적은 것이 된다(출처를 지운다).
 * - 표의 마지막 점 뒤는 그 응력 그대로(완전 소성) — SimEngBay 가 두 솔버로 쟀다(2026-11-28, 「조건_봉_표끝넘어」).
 * - 값은 입력 단위계(응력 MPa)로 적는다 — 내보낼 때 서버가 내보내기 계로 옮긴다.
 * - **해석 케이스에서만** 쓴다(받는 쪽이 v2 로만 받는다). 케이스가 없는 조건이면 고르지 못하게 하고 그렇다고 말한다.
 * - 점검은 서버가 저장할 때 한다(`materials.check_plastic` — 0 < σy, 0 ≤ Et, 표의 변형률은 늘고 응력은 줄지 않는다).
 */

import { useState } from 'react'

import type { MaterialItem } from '@/modules/conditions/api'
import { FrequencyTable } from '@/modules/conditions/FrequencyTable'
import { NumberText } from '@/modules/conditions/NumberText'
import { materialsApi } from '@/modules/materials/api'
import type { PlasticCardRow } from '@/modules/materials/api'
import { Button } from '@/shared/components/ui/button'

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
  source?: string
  card?: { label?: string; orientation?: string; status?: string; fetched_at?: string } | null
}

const STATUS_LABELS: Record<string, string> = { published: '확정', draft: '초안', deprecated: '내려짐' }

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
  const materialId = String(((material.ref ?? {}) as Record<string, unknown>).material_id ?? '')
  const [cards, setCards] = useState<{ items: PlasticCardRow[]; note: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function listCards() {
    setBusy(true)
    setError('')
    try {
      setCards(await materialsApi.plasticCards(materialId))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '카드 목록을 불러오지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }

  async function takeCard(card: PlasticCardRow) {
    setBusy(true)
    setError('')
    try {
      const got = await materialsApi.plasticTable(card.id)
      onChange({ model: got.model, plastic: got.plastic })
      setCards(null)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '카드의 곡선을 받지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }

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
      {model === 'multilinear_isotropic' && plastic.source === 'matnexus' && plastic.card && (
        <p role="status">
          MatNexus 카드 ‘{plastic.card.label}’의 곡선입니다(방향 {plastic.card.orientation}, {STATUS_LABELS[plastic.card.status ?? ''] ?? plastic.card.status}).
          표를 고치면 직접 입력한 곡선이 됩니다.
        </p>
      )}
      {model === 'multilinear_isotropic' && (
        <FrequencyTable
          title="진응력 대 진소성변형률"
          columns={[{ title: '진소성변형률' }, { title: '진응력', unit: stressUnit }]}
          description="첫 행의 소성 변형률은 0이고 그 응력이 항복응력입니다. 소성 변형률은 커지고 응력은 줄지 않아야 합니다."
          plot="linear"
          value={plastic.table}
          onChange={(rows) => set({ table: rows, source: 'manual', card: null })}
        />
      )}
      {model !== 'linear_elastic' && materialId && (
        <div className="space-y-1">
          <Button type="button" size="sm" variant="outline" className="h-7 text-xs" disabled={busy} onClick={() => void listCards()}>
            MatNexus 카드에서 가져오기
          </Button>
          {error && <p className="text-amber-700 dark:text-amber-400">{error}</p>}
          {cards && cards.note && <p className="text-amber-700 dark:text-amber-400">{cards.note}</p>}
          {cards && !cards.note && cards.items.length === 0 && <p className="text-muted-foreground">이 재료에는 소성 곡선 카드가 없습니다.</p>}
          {cards && cards.items.length > 0 && (
            <ul className="space-y-1" aria-label="소성 곡선 카드">
              {cards.items.map((card) => (
                <li key={card.id} className="flex flex-wrap items-center gap-2">
                  <span>
                    방향 {card.orientation || '없음'} · {card.label} · {card.point_count ?? '?'}점 · {STATUS_LABELS[card.status] ?? card.status}
                  </span>
                  {card.usable ? (
                    <Button type="button" size="sm" variant="ghost" className="h-6 text-xs" disabled={busy} onClick={() => void takeCard(card)}>
                      이 곡선 사용
                    </Button>
                  ) : (
                    <span className="text-muted-foreground">{card.why}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {model !== 'linear_elastic' && (
        <p className="text-muted-foreground">
          von Mises 등방 경화로 풉니다. 정적 해석에서만 쓰며 모달, 랜덤 진동은 탄성 값으로 풉니다. 표의 마지막 점 뒤는 그 응력
          그대로(완전 소성)입니다. 해석 쪽(SimEngBay)이 받는 판부터 DOE로 내보낼 수 있습니다.
        </p>
      )}
    </div>
  )
}
