/**
 * 물성 탐색기 — **쪽(族) → 갈래 → 재료 → 물성값** 네 칸.
 *
 * 재료가 백 몇십이고 갈래 하나에 110 건이 몰려 있다. 이름을 아는 사람은 검색하면 되지만,
 * 모르고 찾으러 온 사람은 목록을 끝없이 넘기게 된다 — 그래서 좁혀 들어간다.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import { MaterialPicker } from '@/modules/materials/MaterialPicker'

const CLASSES = {
  fallback: false,
  items: [
    { family: 'Metal', category: 'Steel', count: 110 },
    { family: 'Metal', category: 'Aluminum', count: 1 },
    { family: 'Polymer', category: 'EPDM', count: 9 },
  ],
}

const STEEL = {
  code: 'M-000001',
  id: 'a',
  name: 'SPCC_1.2T_-',
  alias: '냉연강판',
  family: 'Metal',
  category: 'Steel',
  grade: 'SPCC',
  workspace: '기본 부서',
  density: 7850,
  density_unit: 'kg/m^3',
  poisson_ratio: 0.3,
  declared_count: 1,
  source: 'matnexus',
  payload: {
    // 원본은 SI 그대로 — 이것이 감사의 정본이다.
    declared_properties: [
      {
        item: '탄성계수',
        si_unit: 'Pa',
        points: [
          { temperature_C: 22, value_si: 2.06e11 },
          { temperature_C: 400, value_si: 1.7e11 },
        ],
      },
    ],
  },
  /**
   * **서버가 환산해 준다.** 화면은 이것만 보고 그린다 — 환산표를 프런트에도 두면 두 벌이
   * 어긋나고, 그때 보여 준 값과 내보낸 값이 달라진다.
   *
   * **온도 의존 표가 있을 수 있다** — 「값 하나」 로 가정하면 안 된다(강판 상온 206 GPa,
   * 400 °C 170 GPa). 온도가 둘 이상이면 나란히 펼친다.
   */
  converted: {
    system: 'mm-t-s',
    density: 7.85e-9,
    density_unit: 'tonne/mm^3',
    properties: [
      {
        item: '탄성계수',
        unit: 'MPa',
        points: [
          { temperature_C: 22, value: 206000 },
          { temperature_C: 400, value: 170000 },
        ],
      },
    ],
  },
}

let asked: string[] = []
beforeEach(() => {
  asked = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    asked.push(url)
    const body = url.includes('/classifications') ? CLASSES : { fallback: false, items: [STEEL] }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
})

test('쪽 → 갈래로 좁히면 그만큼만 묻는다', async () => {
  render(<MaterialPicker open onClose={() => {}} onPick={() => {}} />)

  // 쪽과 갈래는 **분류에서** 온다 — 목록에서 뽑으면 앞 서른 줄에 있는 쪽만 보인다.
  await waitFor(() => screen.getByRole('button', { name: /Metal/ }))
  expect(asked.some((one) => one.includes('/materials/classifications'))).toBe(true)
  // 개수가 함께 온다 — 빈 갈래를 눌러 보게 하지 않는다. Metal 은 110 + 1.
  expect(screen.getByRole('button', { name: 'Metal 111' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Polymer 9' })).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: 'Metal 111' }))
  // 쪽을 고르면 그 쪽의 갈래만 — Polymer 의 EPDM 은 사라진다.
  await waitFor(() => expect(screen.queryByRole('button', { name: 'EPDM 9' })).toBeNull())
  fireEvent.click(screen.getByRole('button', { name: 'Steel 110' }))

  await waitFor(() => expect(asked.some((one) => one.includes('family=Metal') && one.includes('category=Steel'))).toBe(true))
})

test('재료를 고르면 물성을 그대로 펼치고, 이름 둘을 다 보인다', async () => {
  const picked = vi.fn()
  render(<MaterialPicker open onClose={() => {}} onPick={picked} />)

  await waitFor(() => screen.getByText('냉연강판'))
  // **이름이 둘이다** — 기계가 지은 record_name 과 사람이 읽는 alias. 하나만 보이면
  // 나머지로 기억하던 사람이 못 찾는다.
  expect(screen.getByText('SPCC_1.2T_-')).toBeInTheDocument()
  expect(screen.getByText('M-000001')).toBeInTheDocument()
  // 어느 부서 것인지도 — 두 부서에 같은 이름이 있을 수 있다.
  expect(screen.getByText('기본 부서')).toBeInTheDocument()

  expect(screen.getByRole('button', { name: '이 물성을 쓴다' })).toBeDisabled()
  fireEvent.click(screen.getByText('냉연강판'))
  // 구조를 그대로 — 우리가 아는 항목만 보여 주면 없는 줄 안다.
  await waitFor(() => screen.getByText(/22 °C/))
  expect(screen.getByText('탄성계수')).toBeInTheDocument()
  // **고른 단위계로 보인다.** `2.06e11 Pa` 는 맞는지 눈으로 알 수 없지만 `206000 MPa` 는
  // 안다 — 사람이 검산할 수 있어야 잘못 고른 재료를 잡는다.
  expect(screen.getByText(/206000 MPa/)).toBeInTheDocument()
  expect(screen.getByText(/7\.8500e-9 tonne\/mm\^3/)).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: '이 물성을 쓴다' }))
  expect(picked).toHaveBeenCalledWith(expect.objectContaining({ code: 'M-000001' }))
})

test('분류가 개수를 안 줘도 NaN 을 그리지 않는다', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    const body = url.includes('/classifications')
      ? { fallback: true, items: [{ family: 'Metal', category: 'Steel' }] }
      : { fallback: false, items: [STEEL] }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(<MaterialPicker open onClose={() => {}} onPick={() => {}} />)
  await waitFor(() => screen.getByRole('button', { name: /Metal/ }))
  expect(screen.queryByText(/NaN/)).toBeNull()
})
