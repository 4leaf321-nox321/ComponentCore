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
