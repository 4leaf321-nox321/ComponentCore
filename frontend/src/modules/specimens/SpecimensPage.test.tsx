import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import SpecimensPage from '@/modules/specimens/SpecimensPage'
import { AuthProvider } from '@/shared/auth/AuthContext'

const ME = { id: 'u1', email: 'me@x', display_name: '나', status: 'active', is_system_admin: false, must_change_password: false }

const D790 = {
  id: 'astm-d790-16',
  origin: 'builtin',
  test: 'bending',
  standard: 'ASTM D790',
  name: 'ASTM D790 3점 굽힘 (16:1)',
  preset: {
    id: 'astm-d790-16',
    test: 'bending',
    family: 'bend_bar',
    standard: 'ASTM D790',
    name: 'ASTM D790 3점 굽힘 (16:1)',
    specimen: { length: 127, width: 12.7, thickness: 3.2 },
    setup: { points: 3, span: { to_thickness: 16, value: null }, load_span: null, support_radius: 5, nose_radius: 5, overhang: { to_span: 0.1, min: 6.4 } },
    analysis: { strain: 0.05, friction: 0.1 },
    source: 'ASTM D790: 간격비 16:1',
    verified: false,
    note: '',
  },
}

const ISO = {
  ...D790,
  id: 'iso-178',
  standard: 'ISO 178',
  name: 'ISO 178 3점 굽힘',
  preset: {
    ...D790.preset,
    id: 'iso-178',
    standard: 'ISO 178',
    name: 'ISO 178 3점 굽힘',
    setup: { ...D790.preset.setup, support_radius: [{ max_thickness: 3, radius: 2 }, { radius: 5 }] },
    source: 'ISO 178: R2 = 2.0 mm(h ≤ 3)',
  },
}

type Sent = { method: string; url: string; body?: Record<string, unknown> }

function serve({ admin = false, reject = false }: { admin?: boolean; reject?: boolean } = {}) {
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
    else if (path.endsWith('/specimens/presets') && method === 'GET') out = [D790, ISO]
    else if (path.endsWith('/specimens/presets') && method === 'POST') {
      if (reject) {
        status = 400
        out = { error: { code: 'CCR-SPECIMENS-0002', message: '시험 규격의 값이 올바르지 않습니다.', details: { problems: ['specimen: 시편 길이(50)가 지지 간격(51.2)과 양쪽 돌출을 담지 못합니다(최소 64 mm).'] } } }
      } else out = { ...D790, id: 'new', origin: 'internal' }
    } else if (path.endsWith('/specimens/build')) {
      out = { recipe: { nodes: [] }, conditions: {}, notes: ['규격값을 아직 규격서와 대조하지 않았습니다.'], values: { 지지_간격: 51.2, 지지_반지름: 5, 노즈_반지름: 5, 처짐: 6.8267 } }
    } else if (path.endsWith('/specimens/works')) {
      status = 201
      out = { id: 'w9', name: 'ASTM D790 3점 굽힘 (16:1)' }
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

test('누구나 공개 규격과 그 출처를 보고, 검토 전인 값은 그렇다고 보인다', async () => {
  serve()
  show()
  expect(await screen.findByText('ASTM D790 3점 굽힘 (16:1)')).toBeInTheDocument()
  expect(screen.getByText('ASTM D790: 간격비 16:1')).toBeInTheDocument()
  expect(screen.getAllByText('검토 필요')).toHaveLength(2)
  expect(screen.getAllByText('16 × 두께')).toHaveLength(2)
  expect(screen.getByText('2 (두께 3 이하) / 5 / 5')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '사내 규격으로 복사' })).not.toBeInTheDocument()
})

test('시편 생성은 서버가 계산한 지지 간격과 처짐을 보이고, 만든 작업으로 간다', async () => {
  const sent = serve()
  show()
  fireEvent.click((await screen.findAllByRole('button', { name: '시편 생성' }))[0])
  expect(await screen.findByText(/지지 간격 51.2 mm/)).toBeInTheDocument()
  expect(screen.getByText(/처짐 6.827 mm/)).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('두께 (mm)'), { target: { value: '4' } })
  await waitFor(() => expect(sent.some((one) => one.url.endsWith('/specimens/build') && one.body?.thickness === 4)).toBe(true))
  fireEvent.click(screen.getByRole('button', { name: '생성' }))
  expect(await screen.findByText('작업 화면')).toBeInTheDocument()
  const made = sent.find((one) => one.url.endsWith('/specimens/works'))!
  expect(made.body).toMatchObject({ preset_id: 'astm-d790-16', thickness: 4, fixture: true, conditions: true })
})

test('관리자는 공개 규격을 사내 규격으로 복사하고, 틀린 값은 무엇이 문제인지 본다', async () => {
  const sent = serve({ admin: true, reject: true })
  show()
  fireEvent.click((await screen.findAllByRole('button', { name: '사내 규격으로 복사' }))[1])
  expect(screen.getByLabelText('이름')).toHaveValue('ISO 178 3점 굽힘 (사내)')
  // 두께별 반지름이 그대로 넘어온다.
  expect(screen.getByLabelText('얇은 시편 반지름 (선택)', { selector: '#preset-support-thin' })).toHaveValue(2)
  fireEvent.change(screen.getByLabelText('시편 길이 (mm)'), { target: { value: '50' } })
  fireEvent.click(screen.getByRole('button', { name: '저장' }))
  expect(await screen.findByText(/시편 길이\(50\)가 지지 간격/)).toBeInTheDocument()
  const posted = sent.find((one) => one.method === 'POST' && one.url.endsWith('/specimens/presets'))!
  const preset = posted.body?.preset as Record<string, any>
  expect(preset.specimen.length).toBe(50)
  expect(preset.setup.support_radius).toEqual([{ max_thickness: 3, radius: 2 }, { radius: 5 }])
  expect(preset.verified).toBe(false)
})
