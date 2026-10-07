import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import SpecimensPage from '@/modules/specimens/SpecimensPage'
import { AuthProvider } from '@/shared/auth/AuthContext'

const ME = { id: 'u1', email: 'me@x', display_name: '나', status: 'active', is_system_admin: false, must_change_password: false }

const common = { standard: 'IEC 62368-1', verified: false, note: '' }
const T5 = {
  id: 'iec-62368-1-t5',
  origin: 'builtin',
  test: 'force',
  standard: 'IEC 62368-1',
  name: 'IEC 62368-1 T.5 정하중 250 N',
  preset: { ...common, id: 'iec-62368-1-t5', test: 'force', name: 'IEC 62368-1 T.5 정하중 250 N', source: '지름 30 mm 원형 평면', setup: { force: 250, probe_diameter: 30 }, analysis: { large_deflection: false } },
}
const SINE = {
  id: 'iec-60068-2-6-150-1g',
  origin: 'builtin',
  test: 'vibration',
  standard: 'IEC 60068-2-6',
  name: 'IEC 60068-2-6 정현파 10~150 Hz, 1 g',
  preset: {
    ...common,
    standard: 'IEC 60068-2-6',
    id: 'iec-60068-2-6-150-1g',
    test: 'vibration',
    name: 'IEC 60068-2-6 정현파 10~150 Hz, 1 g',
    source: '심각도 표',
    setup: { freq_min: 10, freq_max: 150, acceleration_g: 1, damping_ratio: 0.02, modes: 20, points: 100 },
  },
}

type Sent = { method: string; url: string; body?: Record<string, unknown> }

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
    else if (path.endsWith('/specimens/presets') && method === 'GET') out = [T5, SINE]
    else if (path.endsWith('/specimens/presets') && method === 'POST') out = { ...T5, id: 'new', origin: 'internal' }
    else if (path.endsWith('/works')) out = { items: [{ id: 'w1', name: '휴대폰 케이스', kind: 'part', current_version: 2 }], total: 1, limit: 100, offset: 0 }
    else if (path.endsWith('/parts')) out = { items: [{ id: 'p1', name: '공용 브래킷', current_version: 1 }], total: 1, limit: 100, offset: 0 }
    else if (path.endsWith('/specimens/product-tests')) {
      status = 201
      out = { id: 'w9', name: '휴대폰 케이스 — IEC 62368-1 T.5 정하중 250 N' }
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

test('정하중 규격을 제품에 적용하면 고른 제품과 누르는 위치로 새 작업을 만든다', async () => {
  const sent = serve()
  show()
  expect(await screen.findByText('IEC 62368-1 T.5 정하중 250 N')).toBeInTheDocument()
  expect(screen.getByText('정하중')).toBeInTheDocument()
  fireEvent.click(screen.getAllByRole('button', { name: '제품에 적용' })[0])
  const select = await screen.findByLabelText('제품')
  await waitFor(() => expect(screen.getByRole('option', { name: '휴대폰 케이스 (v2)' })).toBeInTheDocument())
  expect(screen.getByRole('button', { name: '생성' })).toBeDisabled() // 제품을 고르기 전
  fireEvent.change(select, { target: { value: 'work:w1' } })
  fireEvent.change(screen.getByLabelText('누르는 위치 X (mm)'), { target: { value: '12' } })
  fireEvent.click(screen.getByRole('button', { name: '생성' }))
  expect(await screen.findByText('작업 화면')).toBeInTheDocument()
  const made = sent.find((one) => one.url.endsWith('/specimens/product-tests'))!
  expect(made.body).toMatchObject({ preset_id: 'iec-62368-1-t5', source: 'work:w1', x: 12, y: null })
})

test('진동 규격은 가진 축을 고른다', async () => {
  const sent = serve()
  show()
  fireEvent.click((await screen.findAllByRole('button', { name: '제품에 적용' }))[1])
  const select = await screen.findByLabelText('제품')
  await screen.findByRole('option', { name: '공용 브래킷 (v1)' }) // 목록이 온 뒤에 고른다
  fireEvent.change(select, { target: { value: 'part:p1' } })
  fireEvent.change(screen.getByLabelText('가진 축'), { target: { value: 'x' } })
  expect(screen.queryByLabelText('누르는 위치 X (mm)')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '생성' }))
  await waitFor(() => expect(sent.some((one) => one.url.endsWith('/specimens/product-tests'))).toBe(true))
  expect(sent.find((one) => one.url.endsWith('/specimens/product-tests'))!.body).toMatchObject({ source: 'part:p1', axis: 'x' })
})

test('관리자는 정하중 규격을 사내 규격으로 복사해 값을 고친다', async () => {
  const sent = serve(true)
  show()
  fireEvent.click((await screen.findAllByRole('button', { name: '사내 규격으로 복사' }))[0])
  expect(screen.getByLabelText('이름')).toHaveValue('IEC 62368-1 T.5 정하중 250 N (사내)')
  fireEvent.change(screen.getByLabelText('하중 (N)'), { target: { value: '300' } })
  fireEvent.click(screen.getByRole('button', { name: '저장' }))
  await waitFor(() => expect(sent.some((one) => one.method === 'POST' && one.url.endsWith('/specimens/presets'))).toBe(true))
  const preset = sent.find((one) => one.method === 'POST' && one.url.endsWith('/specimens/presets'))!.body?.preset as Record<string, any>
  expect(preset).toMatchObject({ test: 'force', setup: { force: 300, probe_diameter: 30 }, verified: false })
})
