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
    system: 'mm_n_tonne',
    density: 7.85e-9,
    density_unit: 'tonne/mm3',
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

test('계열 → 분류로 좁히면 그만큼만 조회한다', async () => {
  render(<MaterialPicker open onClose={() => {}} onAdd={() => {}} />)

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

test('재료를 선택하면 물성을 그대로 표시하고, 이름 둘을 모두 표시한다', async () => {
  const picked = vi.fn()
  render(<MaterialPicker open onClose={() => {}} onAdd={picked} />)

  await waitFor(() => screen.getByText('냉연강판'))
  // **이름이 둘이다** — 기계가 지은 record_name 과 사람이 읽는 alias. 하나만 보이면
  // 나머지로 기억하던 사람이 못 찾는다.
  expect(screen.getByText('SPCC_1.2T_-')).toBeInTheDocument()
  expect(screen.getByText('M-000001')).toBeInTheDocument()
  // 어느 부서 것인지도 — 두 부서에 같은 이름이 있을 수 있다.
  expect(screen.getByText('기본 부서')).toBeInTheDocument()

  expect(screen.getByRole('button', { name: '물성 추가' })).toBeDisabled()
  // **줄을 누르면 담긴다** — 작은 확인란을 겨눌 필요가 없다. 값도 함께 보인다.
  fireEvent.click(screen.getByText('냉연강판'))
  expect(screen.getByRole('checkbox', { name: '냉연강판 선택' })).toBeChecked()
  // 구조를 그대로 — 우리가 아는 항목만 보여 주면 없는 줄 안다.
  await waitFor(() => screen.getByText(/22 °C/))
  expect(screen.getByText('탄성계수')).toBeInTheDocument()
  // **고른 단위계로 보인다.** `2.06e11 Pa` 는 맞는지 눈으로 알 수 없지만 `206000 MPa` 는
  // 안다 — 사람이 검산할 수 있어야 잘못 고른 재료를 잡는다.
  expect(screen.getByText(/206000 MPa/)).toBeInTheDocument()
  expect(screen.getByText(/7\.8500e-9 tonne\/mm3/)).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: '물성 추가 (1)' }))
  await waitFor(() => expect(picked).toHaveBeenCalledWith([expect.objectContaining({ code: 'M-000001' })]))
})

test('분류에 개수가 없어도 NaN 을 표시하지 않는다', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    const body = url.includes('/classifications')
      ? { fallback: true, items: [{ family: 'Metal', category: 'Steel' }] }
      : { fallback: false, items: [STEEL] }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(<MaterialPicker open onClose={() => {}} onAdd={() => {}} />)
  await waitFor(() => screen.getByRole('button', { name: /Metal/ }))
  expect(screen.queryByText(/NaN/)).toBeNull()
})

const CAT_CLASSES = {
  fallback: false,
  total: 2663,
  items: [
    { family: 'packaging', category: '', count: 116 },
    { family: '', category: 'composite', count: 739 },
  ],
}
const EMC_ROW = {
  id: 'emc-1',
  code: 'PKG-EMC',
  name: 'Epoxy Molding Compound (EMC)',
  alias: 'Resonac Corporation',
  family: 'packaging',
  category: 'composite',
  grade: 'epoxy molding compound',
  workspace: '문헌',
  density: null,
  density_unit: '',
  poisson_ratio: null,
  declared_count: 0,
  source: 'literature',
  payload: {},
}
const EMC_FULL = {
  ...EMC_ROW,
  declared_count: 2,
  payload: { values: [{}, {}] },
  converted: {
    system: 'mm_n_tonne',
    properties: [
      {
        item: '영률',
        key: 'mechanical.youngs_modulus',
        unit: 'MPa',
        points: [{ temperature_C: null, value: 18330 }],
        tier: 1,
        conditions: { temperature_k: 298 },
      },
    ],
  },
}

test('문헌에서도 선택할 수 있고, 값은 **선택한 뒤에** 조회한다', async () => {
  const seen: string[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    seen.push(url)
    const body = url.includes('/catalog/classifications')
      ? CAT_CLASSES
      : url.includes('/classifications')
        ? CLASSES
        : url.includes('source=literature') && url.includes('/materials/emc-1')
          ? EMC_FULL
          : url.includes('source=literature')
            ? { fallback: false, items: [EMC_ROW] }
            : { fallback: false, items: [STEEL] }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(<MaterialPicker open onClose={() => {}} onAdd={() => {}} />)

  await waitFor(() => screen.getByText('냉연강판'))
  fireEvent.click(screen.getByRole('button', { name: '문헌' }))

  // 창고가 바뀌면 **다른 분류**를 본다 — 하위계 · 갈래다.
  await waitFor(() => expect(seen.some((one) => one.includes('/catalog/classifications'))).toBe(true))
  await waitFor(() => screen.getByRole('button', { name: 'packaging 116' }))
  expect(screen.getByText('분야')).toBeInTheDocument()

  // 목록에는 값이 없다 — 고르면 그때 받는다(2663건을 값째로 끌 수 없다).
  await waitFor(() => screen.getByText('Epoxy Molding Compound (EMC)'))
  expect(screen.getByText('Resonac Corporation')).toBeInTheDocument()
  fireEvent.click(screen.getByText('Epoxy Molding Compound (EMC)'))
  await waitFor(() => expect(seen.some((one) => one.includes('/materials/emc-1'))).toBe(true))

  // 받아 온 값이 고른 단위계로 보이고, **조건과 등급이 함께** 보인다.
  await waitFor(() => screen.getByText(/18330 MPa/))
  expect(screen.getByText(/tier 1/)).toBeInTheDocument()
  expect(screen.getByText(/temperature_k 298/)).toBeInTheDocument()
})

test('여러 개를 담아 **한 번에** 추가한다 — 창고를 바꿔도 담은 것이 남고, 문헌은 값까지 받아 온다', async () => {
  const seen: string[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    seen.push(url)
    const body = url.includes('/catalog/classifications')
      ? CAT_CLASSES
      : url.includes('/classifications')
        ? CLASSES
        : url.includes('source=literature') && url.includes('/materials/emc-1')
          ? EMC_FULL
          : url.includes('source=literature')
            ? { fallback: false, items: [EMC_ROW] }
            : { fallback: false, items: [STEEL] }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  const added = vi.fn()
  render(<MaterialPicker open onClose={() => {}} onAdd={added} />)

  await waitFor(() => screen.getByText('냉연강판'))
  fireEvent.click(screen.getByRole('checkbox', { name: '냉연강판 선택' }))
  fireEvent.click(screen.getByRole('button', { name: '문헌' }))
  await waitFor(() => screen.getByText('Epoxy Molding Compound (EMC)'))
  fireEvent.click(screen.getByRole('checkbox', { name: 'Epoxy Molding Compound (EMC) 선택' }))

  // 무엇을 담았는지 한자리에서 보인다 — 분류를 옮겨 다니며 담기 때문이다.
  expect(screen.getByText('선택 2')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '물성 추가 (2)' }))

  // **문헌은 목록에 값이 없다** — 담은 것은 추가할 때 값까지 받아 온다. 빈 payload 가 실리면
  // 해석 쪽은 물성 없는 재료를 받는다.
  await waitFor(() => expect(added).toHaveBeenCalled())
  expect(seen.some((one) => one.includes('/materials/emc-1'))).toBe(true)
  expect(added.mock.calls[0][0]).toEqual([
    expect.objectContaining({ code: 'M-000001' }),
    expect.objectContaining({ id: 'emc-1', payload: { values: [{}, {}] } }),
  ])
})

test('이미 담긴 재료는 「추가됨」 으로 보이고 다시 담지 않는다', async () => {
  render(<MaterialPicker open onClose={() => {}} onAdd={() => {}} added={['a']} />)
  await waitFor(() => screen.getByText('냉연강판'))

  expect(screen.getByText('추가됨')).toBeInTheDocument()
  const box = screen.getByRole('checkbox', { name: '냉연강판 선택' })
  expect(box).toBeChecked()
  expect(box).toHaveAttribute('aria-disabled', 'true')
  // 눌러도 값만 보이고 담기지 않는다 — 같은 재료가 두 번 실리면 덱 번호가 둘이 된다.
  fireEvent.click(screen.getByText('냉연강판'))
  await waitFor(() => screen.getByText(/206000 MPa/))
  expect(screen.getByRole('button', { name: '물성 추가' })).toBeDisabled()
})

test('줄을 다시 누르면 빠진다', async () => {
  render(<MaterialPicker open onClose={() => {}} onAdd={() => {}} />)
  await waitFor(() => screen.getByText('냉연강판'))

  fireEvent.click(screen.getByText('냉연강판'))
  expect(screen.getByRole('button', { name: '물성 추가 (1)' })).toBeEnabled()
  // 담긴 것은 바닥에도 이름이 보이므로 줄은 제 이름(확인란)으로 집는다.
  fireEvent.click(screen.getByRole('checkbox', { name: '냉연강판 선택' }))
  expect(screen.getByRole('checkbox', { name: '냉연강판 선택' })).not.toBeChecked()
  expect(screen.getByRole('button', { name: '물성 추가' })).toBeDisabled()
})
