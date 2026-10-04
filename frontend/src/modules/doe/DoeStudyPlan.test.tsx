/**
 * 결과 화면의 계획 쪽 — 형상 점검 · 측정값 · 점 더하기 · 설계점 분포.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import type { DoeStudy } from '@/modules/doe/api'
import { DoeStudyView } from '@/modules/doe/DoeStudyView'

vi.mock('@/shared/viewer/PickViewer', () => ({ default: () => <div data-testid="viewer" /> }))
vi.mock('@/shared/viewer/GridViewer', () => ({ GridViewer: () => <div data-testid="grid" /> }))

export const studyOf = (over: Partial<DoeStudy>) =>
  ({
    id: 's1',
    name: '구멍 밀기',
    method: 'factorial',
    seed: 1,
    point_count: 2,
    done: 2,
    failed: 0,
    local_ready: true,
    visibility: 'read',
    owner_name: '김설계',
    requested_by_name: '',
    job: { status: 'done', artifacts: [], progress: [] },
    export_dir_windows: '',
    exported_at: null,
    recipe: { params: { 구멍_x: 0 }, nodes: [] },
    factors: [{ name: '구멍_x', mode: 'list', values: [0, 20] }],
    points: [
      { id: 'a', number: 1, params: { 구멍_x: 0 }, status: 'ok', error: '', step_file: 'points/p0001.step', quality: { warnings: [], notes: [] } },
      {
        id: 'b',
        number: 2,
        params: { 구멍_x: 20 },
        status: 'ok',
        error: '',
        step_file: 'points/p0002.step',
        quality: { warnings: ['벽 두께 0.2 mm (기준 0.5)'], notes: [] },
      },
    ],
    ...over,
  }) as unknown as DoeStudy

export function mockFetch() {
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    const body = url.includes('/server/display') ? { doe_gallery_max: 24, list_page_size: 20 } : {}
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
}

test('형상 점검 — 경고가 있는 점은 표에 수를 적고 내용은 말풍선에, 머리에 몇 점인지', () => {
  mockFetch()
  render(
    <MemoryRouter>
      <DoeStudyView study={studyOf({})} onReload={() => {}} />
    </MemoryRouter>,
  )
  expect(screen.getByText('점검')).toBeInTheDocument()
  expect(screen.getByText('통과')).toBeInTheDocument()
  expect(screen.getByText('경고 1')).toHaveAttribute('title', '벽 두께 0.2 mm (기준 0.5)')
  expect(screen.getByText(/점검 경고 1/)).toBeInTheDocument()
})

test('점 더하기 — 범위를 바꿀 변수만 골라 세어 보고 더하며, 묶음 이력과 다시 보낼 일을 말한다', async () => {
  const calls: { url: string; body: Record<string, unknown> | null }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null })
    const body = url.includes('/server/display')
      ? { doe_gallery_max: 24, list_page_size: 20 }
      : url.includes('/extend')
        ? { batch: { number: 2, method: 'factorial', samples: 2, seed: 2, factors: [], from: 3, to: 3, added: 1, skipped: 1, rejected: 0 }, study: {} }
        : {}
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  const reload = vi.fn()
  const base = studyOf({
    exported_at: '2026-10-03T00:00:00Z',
    export_stale: true,
    batches: [{ number: 2, method: 'lhs', samples: 1, seed: 7, factors: [], from: 3, to: 3, added: 1, skipped: 0 }],
    point_count: 3,
    points: [...studyOf({}).points, { id: 'c', number: 3, params: { 구멍_x: 10 }, status: 'ok', error: '', step_file: 'points/p0003.step', interference: null, metrics: null }],
  })
  render(
    <MemoryRouter>
      <DoeStudyView study={base} onReload={reload} />
    </MemoryRouter>,
  )
  expect(screen.getByText(/내보낸 뒤 설계점이 추가되었습니다/)).toBeInTheDocument()
  expect(screen.getByText(/배치 2: LHS 설계점 1개, 시드 7, p0003–p0003/)).toBeInTheDocument()
  expect(screen.getByText('배치')).toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: '설계점 추가' }))
  fireEvent.change(screen.getByLabelText('추가 방법'), { target: { value: 'factorial' } })
  fireEvent.click(screen.getByLabelText('구멍_x 범위 변경'))
  fireEvent.change(screen.getByLabelText('구멍_x 새 시작'), { target: { value: '10' } })
  expect(await screen.findByText(/기존 설계점과 값이 같은 1개는 제외합니다/)).toBeInTheDocument()
  const dry = calls.filter((c) => c.url.includes('dry_run=true')).at(-1)!
  expect(dry.body).toMatchObject({ method: 'factorial', factors: [{ name: '구멍_x', mode: 'range', start: 10, end: 20, steps: 2 }] })

  fireEvent.click(screen.getByRole('button', { name: '추가' }))
  await waitFor(() => expect(reload).toHaveBeenCalled())
  expect(calls.some((c) => c.url.endsWith('/doe/s1/extend'))).toBe(true)
})

test('측정값 — 정의한 열이 표에 붙고, 못 잰 값은 빈 칸이다', () => {
  mockFetch()
  const base = studyOf({
    measures: [{ name: '부피', kind: 'volume' }],
    points: studyOf({}).points.map((one, i) => ({ ...one, measures: { 부피: i === 0 ? 24000 : null } })),
  })
  render(
    <MemoryRouter>
      <DoeStudyView study={base} onReload={() => {}} />
    </MemoryRouter>,
  )
  expect(screen.getByText('부피')).toHaveAttribute('title', '측정값: 형상에서 측정한 값')
  expect(screen.getByText('24,000')).toBeInTheDocument()
})

test('설계점 분포 — 펼치면 그리고, 점을 누르면 그 점을 하나씩 보기로 고른다', () => {
  mockFetch()
  render(
    <MemoryRouter>
      <DoeStudyView study={studyOf({ factors: [{ name: '구멍_x', mode: 'list', values: [0, 20] }] })} onReload={() => {}} />
    </MemoryRouter>,
  )
  expect(screen.queryByRole('img', { name: '구멍_x' })).toBeNull()
  const details = screen.getByText(/설계점 분포 \(밀집 영역/).closest('details')!
  details.open = true
  fireEvent(details, new Event('toggle'))
  const plot = screen.getByRole('img', { name: '구멍_x' })
  fireEvent.click(plot.querySelectorAll('circle')[1])
  expect(screen.getAllByText('p0002').length).toBeGreaterThan(0)
})

test('멈춘 DOE — 남은 점을 같은 값으로 이어 만든다', async () => {
  const seen: string[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    seen.push(`${init?.method ?? 'GET'} ${String(input)}`)
    const body = String(input).includes('/server/display') ? { doe_gallery_max: 24, list_page_size: 20 } : {}
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  const stopped = studyOf({
    job: { status: 'cancelled', artifacts: [], progress: [] } as never,
    done: 1,
    points: [studyOf({}).points[0], { ...studyOf({}).points[1], status: 'pending', quality: null }],
  })
  render(
    <MemoryRouter>
      <DoeStudyView study={stopped} onReload={() => {}} />
    </MemoryRouter>,
  )
  fireEvent.click(screen.getByRole('button', { name: /남은 설계점 1개 이어서 생성/ }))
  await waitFor(() => expect(seen).toContain('POST /api/doe/s1/rerun?only=failed'))
})
