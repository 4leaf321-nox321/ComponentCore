import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import SpecimensPage from '@/modules/specimens/SpecimensPage'
import { AuthProvider } from '@/shared/auth/AuthContext'

const ME = { id: 'u1', email: 'me@x', display_name: '나', status: 'active', is_system_admin: false, must_change_password: false }

const bend = (id: string, name: string, origin: 'builtin' | 'internal', extra: Record<string, unknown> = {}) => ({
  id,
  origin,
  test: 'bending',
  standard: 'ASTM D790',
  name,
  ...extra,
  preset: {
    id,
    test: 'bending',
    family: 'bend_bar',
    standard: 'ASTM D790',
    name,
    specimen: { length: 127, width: 12.7, thickness: 3.2 },
    setup: { points: 3, span: { to_thickness: 16, value: null }, load_span: null, support_radius: 5, nose_radius: 5 },
    analysis: { strain: 0.05, friction: 0.1 },
    source: origin === 'internal' ? '사내 시험법 TM-12' : 'ASTM D790: 간격비 16:1',
    verified: origin === 'internal',
    note: '',
  },
})
const T5 = {
  id: 'iec-62368-1-t5',
  origin: 'builtin',
  test: 'force',
  standard: 'IEC 62368-1',
  name: 'IEC 62368-1 T.5 정하중 250 N',
  preset: { id: 'iec-62368-1-t5', test: 'force', standard: 'IEC 62368-1', name: 'IEC 62368-1 T.5 정하중 250 N', source: '지름 30 mm', verified: false, note: '', setup: { force: 250, probe_diameter: 30 }, analysis: { large_deflection: false } },
}
const ROWS = [
  bend('astm-d790-16', 'ASTM D790 3점 굽힘 (16:1)', 'builtin'),
  bend('u-1', 'ASTM D790 (사내 TM-12)', 'internal', { updated_by_name: '관리자', updated_at: '2026-10-05T03:00:00Z' }),
  T5,
]

function show() {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const path = new URL(String(input), 'http://x').pathname
    const out = path.endsWith('/auth/refresh') ? { access_token: 't', expires_in: 900, user: ME } : ROWS
    return new Response(JSON.stringify(out), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(
    <AuthProvider>
      <MemoryRouter>
        <SpecimensPage />
      </MemoryRouter>
    </AuthProvider>,
  )
}

test('사내 규격은 배지 · 줄 바탕 · 수정한 사람으로 공개 규격과 구분된다', async () => {
  show()
  const internal = (await screen.findByText('ASTM D790 (사내 TM-12)')).closest('tr')!
  expect(within(internal).getByText('사내 규격')).toBeInTheDocument()
  expect(within(internal).getByText(/관리자 · .* 수정/)).toBeInTheDocument()
  expect(internal.className).toContain('bg-sky')
  const builtin = screen.getByText('ASTM D790 3점 굽힘 (16:1)').closest('tr')!
  expect(within(builtin).queryByText('사내 규격')).not.toBeInTheDocument()
  expect(screen.getByText('공개 규격 2개 · 사내 규격 1개 · 검토 필요 2개')).toBeInTheDocument()
  // 규격 번호마다 묶음 머리줄
  expect(screen.getByText('ASTM D790', { selector: 'td' })).toHaveTextContent('ASTM D790 · 2개')
})

test('검색어 · 구분 · 시험 종류로 좁히고, 탭은 남은 개수를 보인다', async () => {
  show()
  await screen.findByText('IEC 62368-1 T.5 정하중 250 N')
  expect(screen.getByRole('tab', { name: '전체 3' })).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: '정하중 1' })).toBeInTheDocument()

  fireEvent.change(screen.getByLabelText('구분 필터'), { target: { value: 'internal' } })
  expect(screen.queryByText('ASTM D790 3점 굽힘 (16:1)')).not.toBeInTheDocument()
  expect(screen.getByText('ASTM D790 (사내 TM-12)')).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: '굽힘 1' })).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: '필터 초기화' }))
  fireEvent.change(screen.getByLabelText('검색'), { target: { value: '62368' } })
  await waitFor(() => expect(screen.queryByText('ASTM D790 3점 굽힘 (16:1)')).not.toBeInTheDocument())
  expect(screen.getByText('IEC 62368-1 T.5 정하중 250 N')).toBeInTheDocument()

  fireEvent.change(screen.getByLabelText('검색'), { target: { value: '없는 규격' } })
  expect(await screen.findByText('조건에 맞는 규격이 없습니다')).toBeInTheDocument()
})
