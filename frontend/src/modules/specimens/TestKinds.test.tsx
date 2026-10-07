import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import SpecimensPage from '@/modules/specimens/SpecimensPage'
import { AuthProvider } from '@/shared/auth/AuthContext'

// 3D 는 jsdom 에서 그리지 못한다 — 면 하나를 「누르는」 단추로 바꾼다.
vi.mock('@/shared/viewer/PickViewer', () => ({
  default: ({ onMeasure }: { onMeasure?: (pick: unknown) => void }) => (
    <button type="button" onClick={() => onMeasure?.({ kind: 'face', face: { index: 3, kind: 'plane', center: [1.23456, 2, 12], normal: [0, 0, 1], area: 10, vertices: [], triangles: [] } })}>
      윗면 누르기
    </button>
  ),
}))

const ME = { id: 'u1', email: 'me@x', display_name: '나', status: 'active', is_system_admin: false, must_change_password: false }
const common = { verified: false, note: '' }

function row(preset: Record<string, unknown>) {
  return { id: preset.id, origin: 'builtin', test: preset.test, standard: preset.standard, name: preset.name, preset }
}

const D638 = row({
  ...common,
  id: 'astm-d638-type-i',
  test: 'tensile',
  family: 'dogbone',
  standard: 'ASTM D638',
  name: 'ASTM D638 Type I',
  source: 'Fig. 1 Type I',
  specimen: { length: 165, width: 19, thickness: 3.2, gauge_length: 50, grip_length: 25, gauge_width: 13, parallel_length: 57, radius: 76 },
  analysis: { strain: 0.01, large_deflection: false },
})
const HANDLE = row({ ...common, id: 'iec-62368-1-8.8-handle', test: 'handle', standard: 'IEC 62368-1', name: '손잡이 강도 (무게의 4배)', source: '8.8', setup: { weight_factor: 4 }, analysis: { large_deflection: false } })
const STACK = row({ ...common, id: 'ista-stack-5x3', test: 'compression', standard: 'ISTA', name: '5단 · 계수 3 (예시)', source: '적재식', setup: { layers: 5, stack_height: null, factor: 3 }, analysis: { large_deflection: false } })
const FREE = row({ ...common, id: 'astm-e1876-free', test: 'modal', standard: 'ASTM E1876', name: '자유-자유 공진', source: 'E1876', setup: { modes: 6, freq_min: 0, freq_max: null, support: 'free' } })
const CORD = row({ ...common, id: 'iec-60335-1-cord-1kg', test: 'directed', standard: 'IEC 60335-1', name: '코드 고정 (30 N, 0.1 N·m)', source: '25.15', setup: { force: 30, torque: 0.1 }, analysis: { large_deflection: false } })
const SHOCK = row({ ...common, id: 'iec-60068-2-27-50g-11ms', test: 'acceleration', standard: 'IEC 60068-2-27', name: '반정현파 50 g', source: '심각도 표', setup: { acceleration_g: 50, duration_ms: 11, factor: 1 }, analysis: { large_deflection: false } })
const E9 = row({ ...common, id: 'astm-e9-short', test: 'compressive', family: 'cylinder', standard: 'ASTM E9', name: 'E9 짧은 원기둥', source: 'E9 표', specimen: { length: 25, width: 30, thickness: null }, analysis: { strain: 0.01, large_deflection: false } })

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
    else if (path.endsWith('/specimens/presets') && method === 'GET') out = [D638, HANDLE, STACK, FREE, CORD, SHOCK, E9]
    else if (path.endsWith('/specimens/presets') && method === 'POST') out = { ...D638, id: 'new', origin: 'internal' }
    else if (path.endsWith('/specimens/build')) out = { recipe: { version: 1, nodes: [] }, conditions: null, notes: ['검토 필요'], values: { 전이_길이: 21.1423, 늘림: 1.15 } }
    else if (path.endsWith('/specimens/product-mesh')) out = { summary: { bbox: { min: [0, 0, 0], max: [1, 1, 1] } }, mesh: { bbox: { min: [0, 0, 0], max: [1, 1, 1] }, faces: [], edges: [] } }
    else if (path.endsWith('/works') && method === 'GET') out = { items: [{ id: 'w1', name: '휴대폰 케이스', kind: 'part', current_version: 2 }], total: 1, limit: 100, offset: 0 }
    else if (path.endsWith('/parts')) out = { items: [], total: 0, limit: 100, offset: 0 }
    else if (path.endsWith('/specimens/works') || path.endsWith('/specimens/product-tests')) {
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

const last = (sent: Sent[], tail: string) => [...sent].reverse().find((one) => one.url.endsWith(tail))

/** 그 규격의 줄에 있는 단추 — 종류가 늘면 순서가 바뀌므로 이름으로 찾는다. */
async function press(name: string, button: string) {
  const line = (await screen.findByText(name)).closest('tr')!
  fireEvent.click(within(line).getByRole('button', { name: button }))
}

async function chooseProduct() {
  const select = await screen.findByLabelText('제품')
  await screen.findByRole('option', { name: '휴대폰 케이스 (v2)' }) // 목록이 온 뒤에 고른다
  fireEvent.change(select, { target: { value: 'work:w1' } })
}

test('종류마다 표가 따로 있고 탭이 개수를 보인다', async () => {
  serve()
  show()
  expect(await screen.findByText('ASTM D638 Type I')).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: '인장 1' })).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: '고유진동수 1' })).toBeInTheDocument()
  expect(screen.getByText('폭 13 · 길이 57 · R76')).toBeInTheDocument()
  expect(screen.getByText('4배')).toBeInTheDocument()
  expect(screen.getByText('자유-자유')).toBeInTheDocument()
})

test('인장 시편은 치수를 고치면 서버가 그려 본 값을 보이고, 바꾼 치수로 만든다', async () => {
  const sent = serve()
  show()
  await press('ASTM D638 Type I', '시편 생성')
  expect(await screen.findByText(/전이부 길이 21.142 mm/)).toBeInTheDocument()
  expect(screen.getByLabelText('평행부 폭 (mm)')).toHaveValue(13)
  fireEvent.change(screen.getByLabelText('평행부 폭 (mm)'), { target: { value: '10' } })
  await waitFor(() => expect(last(sent, '/specimens/build')?.body?.dimensions.gauge_width).toBe(10))
  fireEvent.click(screen.getByRole('button', { name: '생성' }))
  expect(await screen.findByText('작업 화면')).toBeInTheDocument()
  expect(last(sent, '/specimens/works')?.body).toMatchObject({ preset_id: 'astm-d638-type-i', dimensions: { gauge_width: 10, radius: 76 }, fixture: true })
})

test('손잡이 시험은 3D 에서 고정 자리를 골라야 만들 수 있다', async () => {
  const sent = serve()
  show()
  await press('손잡이 강도 (무게의 4배)', '제품에 적용')
  await chooseProduct()
  expect(screen.getByText('꼭 고르십시오')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '생성' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: '고정 자리 고르기' }))
  fireEvent.click(await screen.findByRole('button', { name: '윗면 누르기' }))
  expect(screen.getByText('면 1개')).toBeInTheDocument()
  expect(last(sent, '/specimens/product-mesh')?.body).toEqual({ source: 'work:w1' })
  fireEvent.click(screen.getByRole('button', { name: '생성' }))
  expect(await screen.findByText('작업 화면')).toBeInTheDocument()
  expect(last(sent, '/specimens/product-tests')?.body).toMatchObject({
    preset_id: 'iec-62368-1-8.8-handle',
    faces: { support: [{ point: [1.235, 2, 12], normal: [0, 0, 1], kind: 'plane' }] },
    axis: null,
  })
})

test('같은 면을 다시 누르면 빠지고, 적층 압축은 무게를 받는다', async () => {
  const sent = serve()
  show()
  await press('손잡이 강도 (무게의 4배)', '제품에 적용')
  await chooseProduct()
  fireEvent.click(screen.getByRole('button', { name: '고정 자리 고르기' }))
  const face = await screen.findByRole('button', { name: '윗면 누르기' })
  fireEvent.click(face)
  fireEvent.click(face)
  expect(screen.getByText('꼭 고르십시오')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '취소' }))

  await press('5단 · 계수 3 (예시)', '제품에 적용')
  await chooseProduct()
  expect(screen.getByRole('button', { name: '생성' })).toBeDisabled() // 무게 전
  fireEvent.change(screen.getByLabelText('제품 무게 (kg)'), { target: { value: '1.5' } })
  fireEvent.click(screen.getByRole('button', { name: '생성' }))
  await waitFor(() => expect(last(sent, '/specimens/product-tests')).toBeDefined())
  expect(last(sent, '/specimens/product-tests')?.body).toMatchObject({ preset_id: 'ista-stack-5x3', mass: 1.5, faces: {} })
})

test('관리자는 인장 규격을 칸 정의대로 복사해 고친다', async () => {
  const sent = serve(true)
  show()
  await press('ASTM D638 Type I', '사내 규격으로 복사')
  expect(screen.getByLabelText('이름')).toHaveValue('ASTM D638 Type I (사내)')
  fireEvent.change(screen.getByLabelText('전이 반지름 (mm)'), { target: { value: '60' } })
  fireEvent.click(screen.getByLabelText('대변형 해석'))
  fireEvent.click(screen.getByRole('button', { name: '저장' }))
  await waitFor(() => expect(sent.some((one) => one.method === 'POST' && one.url.endsWith('/specimens/presets'))).toBe(true))
  const preset = sent.find((one) => one.method === 'POST' && one.url.endsWith('/specimens/presets'))!.body?.preset
  expect(preset).toMatchObject({ test: 'tensile', family: 'dogbone', specimen: { radius: 60, gauge_width: 13 }, analysis: { strain: 0.01, large_deflection: true }, verified: false })
  expect(preset.id).toBeUndefined()
})

test('방향 하중은 고른 면과 방향을 보낸다 — 기본은 바깥으로 당김, 고르면 누름', async () => {
  const sent = serve()
  show()
  await press('코드 고정 (30 N, 0.1 N·m)', '제품에 적용')
  await chooseProduct()
  expect(screen.getByRole('button', { name: '생성' })).toBeDisabled() // 하중 면 전
  fireEvent.click(screen.getByRole('button', { name: '하중 면 고르기' }))
  fireEvent.click(await screen.findByRole('button', { name: '윗면 누르기' }))
  fireEvent.click(screen.getByRole('button', { name: '생성' }))
  await waitFor(() => expect(last(sent, '/specimens/product-tests')).toBeDefined())
  expect(last(sent, '/specimens/product-tests')?.body).toMatchObject({ faces: { load: [{ normal: [0, 0, 1] }] }, direction: [0, 0, 1] })
})

test('방향을 누름으로 바꾸면 법선의 반대로 보낸다', async () => {
  const sent = serve()
  show()
  await press('코드 고정 (30 N, 0.1 N·m)', '제품에 적용')
  await chooseProduct()
  fireEvent.click(screen.getByRole('button', { name: '하중 면 고르기' }))
  fireEvent.click(await screen.findByRole('button', { name: '윗면 누르기' }))
  fireEvent.change(screen.getByLabelText('하중 방향'), { target: { value: 'push' } })
  fireEvent.click(screen.getByRole('button', { name: '생성' }))
  await waitFor(() => expect(last(sent, '/specimens/product-tests')).toBeDefined())
  expect(last(sent, '/specimens/product-tests')?.body?.direction).toEqual([0, 0, -1])
  expect(await screen.findByText('작업 화면')).toBeInTheDocument()
})

test('등가 가속도는 가속 방향을 고른다', async () => {
  const sent = serve()
  show()
  await press('반정현파 50 g', '제품에 적용')
  await chooseProduct()
  fireEvent.change(screen.getByLabelText('가속 방향'), { target: { value: 'y' } })
  fireEvent.click(screen.getByRole('button', { name: '생성' }))
  await waitFor(() => expect(last(sent, '/specimens/product-tests')).toBeDefined())
  expect(last(sent, '/specimens/product-tests')?.body).toMatchObject({ preset_id: 'iec-60068-2-27-50g-11ms', axis: 'y', faces: {} })
  expect(await screen.findByText('작업 화면')).toBeInTheDocument()
})

test('원기둥 압축 시편은 두께 칸이 없다', async () => {
  serve()
  show()
  expect(await screen.findByText('Ø30 × 25')).toBeInTheDocument()
  await press('E9 짧은 원기둥', '시편 생성')
  expect(await screen.findByLabelText('폭 · 지름 (mm)')).toHaveValue(30)
  expect(screen.queryByLabelText('두께 (mm)')).not.toBeInTheDocument()
})
