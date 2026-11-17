import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import type { RandomPreset, VibrationPreset } from '@/modules/specimens/api'
import { crossover, kindOf } from '@/modules/specimens/kinds'
import SpecimensPage from '@/modules/specimens/SpecimensPage'
import { AuthProvider } from '@/shared/auth/AuthContext'

// 진동 시험 규격의 가진 프로파일(2026-11-17) — 정현파의 변위 진폭 · 교차 주파수, 랜덤 진동의 PSD 표.

const ME = { id: 'u1', email: 'me@x', display_name: '나', status: 'active', is_system_admin: false, must_change_password: false }
const common = { verified: false, note: '' }

const SINE: VibrationPreset = {
  ...common,
  id: 'iec-60068-2-6-150-1g',
  test: 'vibration',
  standard: 'IEC 60068-2-6',
  name: 'IEC 60068-2-6 정현파 10~150 Hz, 1 g',
  source: '심각도 표',
  setup: { freq_min: 10, freq_max: 150, acceleration_g: 1, displacement_mm: 0.075, damping_ratio: 0.02, modes: 20, points: 100 },
}
const RANDOM: RandomPreset = {
  ...common,
  id: 'iec-60068-2-64-example-6g',
  test: 'random',
  standard: 'IEC 60068-2-64',
  name: 'IEC 60068-2-64 꼴 예시 20~2000 Hz, 6.06 Grms',
  source: '예시',
  setup: {
    psd: [
      [20, 0.01],
      [80, 0.04],
      [350, 0.04],
      [2000, 0.007],
    ],
    grms: 6.06,
    damping_ratio: 0.02,
    modes: 40,
  },
}

const row = (preset: VibrationPreset | RandomPreset) => ({ id: preset.id, origin: 'builtin', test: preset.test, standard: preset.standard, name: preset.name, preset })

test('정현파의 교차 주파수는 서버와 같은 식이다', () => {
  // √(9806.65 / 0.075) / 2π — 서버 `VibrationSetup.crossover` 도 57.55.
  expect(crossover(SINE.setup)).toBeCloseTo(57.55, 2)
  expect(crossover({ ...SINE.setup, displacement_mm: null })).toBeNull()
  const sine = kindOf('vibration')!
  expect(sine.summary(SINE)).toContain('교차 주파수 57.6 Hz 아래는 변위 0.075 mm, 위는 1 g가 일정합니다')
  expect(sine.summary({ ...SINE, setup: { ...SINE.setup, displacement_mm: null } })).toContain('1 g를 10~150 Hz에서 가진합니다')
  expect(sine.summary({ ...SINE, setup: { ...SINE.setup, freq_min: 5, freq_max: 40 } })).toContain('범위 전체가 교차 주파수 57.6 Hz 아래')
})

test('랜덤 진동은 표의 범위와 Grms 를 보인다', () => {
  const random = kindOf('random')!
  expect(random.columns.map((one) => one.text(RANDOM))).toEqual(['20~2000', '6.06', '0.02'])
  expect(random.summary(RANDOM)).toBe('받침을 고정하고 한 축으로 가속도 PSD 20~2000 Hz(Grms 6.06 g)를 겁니다(감쇠비 0.02).')
})

type Sent = { method: string; url: string; body?: Record<string, any> }

function serve(admin = false) {
  const sent: Sent[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    const body = init?.body ? JSON.parse(String(init.body)) : undefined
    sent.push({ method, url, body })
    const path = new URL(url, 'http://x').pathname
    let status = 200
    let out: unknown = {}
    if (path.endsWith('/auth/refresh')) out = { access_token: 't', expires_in: 900, user: { ...ME, is_system_admin: admin } }
    else if (path.endsWith('/specimens/presets') && method === 'GET') out = [row(SINE), row(RANDOM)]
    else if (path.endsWith('/specimens/presets') && method === 'POST') out = { ...row(RANDOM), id: 'new', origin: 'internal' }
    else if (path.endsWith('/works')) out = { items: [{ id: 'w1', name: '휴대폰 케이스', kind: 'part', current_version: 2 }], total: 1, limit: 100, offset: 0 }
    else if (path.endsWith('/parts')) out = { items: [], total: 0, limit: 100, offset: 0 }
    else if (path.endsWith('/specimens/product-tests')) {
      status = 201
      out = { id: 'w9', name: '새 작업' }
    }
    return new Response(JSON.stringify(out), { status, headers: { 'Content-Type': 'application/json' } })
  })
  return sent
}

function show() {
  render(
    <AuthProvider>
      <MemoryRouter initialEntries={['/specimens']}>
        <Routes>
          <Route path="/specimens" element={<SpecimensPage />} />
          <Route path="/works/:id" element={<p>작업 화면</p>} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  )
}

async function press(name: string, button: string) {
  const line = (await screen.findByText(name)).closest('tr')!
  fireEvent.click(within(line).getByRole('button', { name: button }))
}

test('랜덤 진동 규격도 가진 축을 골라 제품에 건다', async () => {
  const sent = serve()
  show()
  await press(RANDOM.name, '제품에 적용')
  const select = await screen.findByLabelText('제품')
  await screen.findByRole('option', { name: '휴대폰 케이스 (v2)' })
  fireEvent.change(select, { target: { value: 'work:w1' } })
  fireEvent.change(screen.getByLabelText('가진 축'), { target: { value: 'y' } })
  fireEvent.click(screen.getByRole('button', { name: '생성' }))
  await waitFor(() => expect(sent.some((one) => one.url.endsWith('/specimens/product-tests'))).toBe(true))
  expect(sent.find((one) => one.url.endsWith('/specimens/product-tests'))!.body).toMatchObject({ preset_id: RANDOM.id, axis: 'y' })
})

test('관리자는 랜덤 규격을 복사해 PSD 표를 붙여 넣고 고친다', async () => {
  const sent = serve(true)
  show()
  await press(RANDOM.name, '사내 규격으로 복사')
  expect(await screen.findByText('Grms 6.06 g')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '모두 지우기' }))
  // 시험 사양서의 표를 엑셀에서 복사한 글 — 머리글 줄은 건너뛴다.
  fireEvent.change(screen.getByLabelText('PSD 표 붙여넣기'), { target: { value: 'Hz\tg²/Hz\n20\t0.04\n2000\t0.04' } })
  expect(await screen.findByText('Grms 8.90 g')).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText(/규격의 Grms \(g\)/), { target: { value: '8.9' } })
  fireEvent.click(screen.getByRole('button', { name: '저장' }))
  await waitFor(() => expect(sent.some((one) => one.method === 'POST' && one.url.endsWith('/specimens/presets'))).toBe(true))
  const preset = sent.find((one) => one.method === 'POST' && one.url.endsWith('/specimens/presets'))!.body?.preset
  expect(preset).toMatchObject({
    test: 'random',
    setup: {
      psd: [
        [20, 0.04],
        [2000, 0.04],
      ],
      grms: 8.9,
      damping_ratio: 0.02,
      modes: 40,
    },
  })
})

test('IEC 의 (m/s²)²/Hz 표는 붙여 넣은 뒤 g²/Hz 로 바꿔 저장한다', async () => {
  const sent = serve(true)
  show()
  await press(RANDOM.name, '사내 규격으로 복사')
  fireEvent.click(await screen.findByRole('button', { name: '모두 지우기' }))
  fireEvent.change(screen.getByLabelText('PSD 표 붙여넣기'), { target: { value: '20\t3.8466\n2000\t3.8466' } })
  fireEvent.click(await screen.findByRole('button', { name: '(m/s²)²/Hz → g²/Hz' }))
  expect(await screen.findByText('Grms 8.90 g')).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText(/규격의 Grms \(g\)/), { target: { value: '' } })
  fireEvent.click(screen.getByRole('button', { name: '저장' }))
  await waitFor(() => expect(sent.some((one) => one.method === 'POST' && one.url.endsWith('/specimens/presets'))).toBe(true))
  const preset = sent.find((one) => one.method === 'POST' && one.url.endsWith('/specimens/presets'))!.body?.preset
  expect(preset.setup).toMatchObject({
    psd: [
      [20, 0.0399978],
      [2000, 0.0399978],
    ],
    grms: null,
  })
})

test('관리자는 정현파 규격의 변위 진폭을 비울 수 있다', async () => {
  const sent = serve(true)
  show()
  await press(SINE.name, '사내 규격으로 복사')
  expect(screen.getByLabelText(/변위 진폭 \(mm\)/)).toHaveValue(0.075)
  fireEvent.change(screen.getByLabelText(/변위 진폭 \(mm\)/), { target: { value: '' } })
  fireEvent.click(screen.getByRole('button', { name: '저장' }))
  await waitFor(() => expect(sent.some((one) => one.method === 'POST' && one.url.endsWith('/specimens/presets'))).toBe(true))
  const preset = sent.find((one) => one.method === 'POST' && one.url.endsWith('/specimens/presets'))!.body?.preset
  expect(preset.setup).toMatchObject({ acceleration_g: 1, displacement_mm: null })
})
