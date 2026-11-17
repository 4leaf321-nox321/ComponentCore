import { render, screen } from '@testing-library/react'

import { MaterialProperties, usedPoint } from '@/modules/materials/MaterialProperties'
import type { MaterialConverted } from '@/modules/materials/api'

// 온도별 물성(2026-11-17) — 받는 쪽(SimEngBay)은 환경 온도(없으면 22 °C)에 가장 가까운 점 하나를 쓴다(보간 없음).

const STEEL: MaterialConverted = {
  system: 'mm_n_tonne',
  density: 7.85e-9,
  density_unit: 'tonne/mm3',
  poisson_ratio: 0.3,
  properties: [
    {
      item: '탄성계수',
      key: 'mechanical.youngs_modulus',
      unit: 'MPa',
      points: [
        { temperature_C: 22, value: 206000 },
        { temperature_C: 200, value: 190000 },
        { temperature_C: 400, value: 170000 },
      ],
    },
    { item: '비열', key: 'thermal.specific_heat', unit: 'mJ/(tonne.K)', points: [{ temperature_C: null, value: 4.7e8 }] },
  ],
}

test('기준 온도에 가장 가까운 점 — 온도가 둘 이상 적혔을 때만', () => {
  const points = STEEL.properties![0].points
  expect(usedPoint(points, 22)).toBe(0)
  expect(usedPoint(points, 150)).toBe(1)
  expect(usedPoint(points, 1000)).toBe(2)
  // 같은 거리면 앞(낮은 온도) 쪽 — 받는 쪽의 규칙과 맞춘다.
  expect(usedPoint(points, 300)).toBe(1)
  expect(usedPoint(STEEL.properties![1].points, 22)).toBeNull()
})

test('해석에 쓰이는 값을 굵게 보이고, 어느 온도 기준인지 말한다', () => {
  const { rerender } = render(<MaterialProperties converted={STEEL} temperature={350} />)
  expect(screen.getByTitle('해석에 쓰는 값')).toHaveTextContent('400 °C 170000 MPa')
  expect(screen.getByText(/350 °C\(초기조건 ‘환경 온도’, 없으면 22 °C\)에 가장 가까운 값/)).toBeInTheDocument()
  // 환경 온도가 식이면 설계점마다 다르다 — 고르지 않고 그렇다고만.
  rerender(<MaterialProperties converted={STEEL} temperature="formula" />)
  expect(screen.queryByTitle('해석에 쓰는 값')).toBeNull()
  expect(screen.getByText(/환경 온도가 식이라 설계점마다 다릅니다/)).toBeInTheDocument()
  // 탐색기(기준 온도를 모름)는 예전처럼 나란히만.
  rerender(<MaterialProperties converted={STEEL} />)
  expect(screen.getByText('22 °C 206000 MPa · 200 °C 190000 MPa · 400 °C 170000 MPa')).toBeInTheDocument()
})
