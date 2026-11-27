import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'

import type { MaterialItem } from '@/modules/conditions/api'
import { PlasticEditor } from '@/modules/conditions/PlasticEditor'

const STEEL: MaterialItem = { ref: { name: '강' }, apply_to: ['전체'], payload: {} }

function Harness({ enabled, seen }: { enabled: boolean; seen: (next: MaterialItem) => void }) {
  const [material, setMaterial] = useState<MaterialItem>(STEEL)
  return (
    <PlasticEditor
      material={material}
      enabled={enabled}
      onChange={(patch) => {
        const next = { ...material, ...patch }
        setMaterial(next)
        seen(next)
      }}
    />
  )
}

test('케이스가 없는 조건에서는 선형 탄성만 — 고르지 못하고 까닭을 말한다', () => {
  render(<Harness enabled={false} seen={vi.fn()} />)
  expect(screen.getByLabelText('재료 모델', { selector: 'select' })).toBeDisabled()
  expect(screen.getByText(/소성은 해석 케이스에서 지정합니다/)).toBeInTheDocument()
})

test('이선형은 항복응력 · 접선계수를, 다선형은 진응력 대 진소성변형률 표를 적는다 — 선형으로 돌리면 소성 값을 지운다', () => {
  const seen = vi.fn()
  render(<Harness enabled seen={seen} />)
  const select = screen.getByLabelText('재료 모델', { selector: 'select' })
  fireEvent.change(select, { target: { value: 'bilinear_isotropic' } })
  fireEvent.change(screen.getByLabelText('항복응력'), { target: { value: '250' } })
  fireEvent.change(screen.getByLabelText('접선계수'), { target: { value: '=경화' } })
  expect(seen).toHaveBeenLastCalledWith({ ...STEEL, model: 'bilinear_isotropic', plastic: { yield_stress: 250, tangent_modulus: '=경화' } })

  fireEvent.change(select, { target: { value: 'multilinear_isotropic' } })
  expect(screen.getByText('진응력 대 진소성변형률')).toBeInTheDocument()
  expect(seen).toHaveBeenLastCalledWith({ ...STEEL, model: 'multilinear_isotropic', plastic: {} })

  fireEvent.change(select, { target: { value: 'linear_elastic' } })
  expect(seen).toHaveBeenLastCalledWith({ ...STEEL, model: 'linear_elastic', plastic: null })
})

test('MatNexus 카드에서 방향을 골라 곡선을 받는다 — 확정 카드만 고르고, 표를 고치면 직접 입력한 곡선이 된다', async () => {
  const { materialsApi } = await import('@/modules/materials/api')
  vi.spyOn(materialsApi, 'plasticCards').mockResolvedValue({
    note: '',
    items: [
      { id: 'c1', code: 'C-1', label: '인장 MD', test_type: 'tensile', orientation: 'MD', status: 'published', point_count: 3, published_at: null, usable: true, why: '' },
      { id: 'c2', code: 'C-2', label: '인장 TD', test_type: 'tensile', orientation: 'TD', status: 'draft', point_count: 3, published_at: null, usable: false, why: '초안입니다. MatNexus에서 확정(published)된 카드만 해석에 사용합니다.' },
    ],
  })
  vi.spyOn(materialsApi, 'plasticTable').mockResolvedValue({
    model: 'multilinear_isotropic',
    plastic: {
      table: [[0, 250], [0.05, 300]],
      source: 'matnexus',
      card: { id: 'c1', label: '인장 MD', orientation: 'MD', status: 'published', fetched_at: '2026-11-28T00:00:00+00:00' },
    },
  })
  const seen = vi.fn()
  function Box() {
    const [material, setMaterial] = useState<MaterialItem>({ ...STEEL, ref: { name: '강', material_id: 'm1' }, model: 'multilinear_isotropic', plastic: {} })
    return (
      <PlasticEditor
        material={material}
        enabled
        onChange={(patch) => {
          const next = { ...material, ...patch }
          setMaterial(next)
          seen(next)
        }}
      />
    )
  }
  render(<Box />)
  fireEvent.click(screen.getByRole('button', { name: 'MatNexus 카드에서 가져오기' }))
  expect(await screen.findByText(/방향 TD · 인장 TD/)).toBeInTheDocument()
  expect(screen.getByText(/초안입니다/)).toBeInTheDocument()
  expect(screen.getAllByRole('button', { name: '이 곡선 사용' })).toHaveLength(1)
  fireEvent.click(screen.getByRole('button', { name: '이 곡선 사용' }))
  expect(await screen.findByRole('status')).toHaveTextContent('MatNexus 카드 ‘인장 MD’의 곡선입니다(방향 MD, 확정)')
  expect(materialsApi.plasticTable).toHaveBeenCalledWith('c1')
  const last = seen.mock.calls[seen.mock.calls.length - 1][0] as MaterialItem
  expect((last.plastic as { source: string }).source).toBe('matnexus')
})
