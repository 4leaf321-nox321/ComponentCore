import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import type { DoeStudy } from '@/modules/doe/api'
import { DoeStudyView } from '@/modules/doe/DoeStudyView'
import { mergeMeshes } from '@/modules/doe/PointsGallery'

vi.mock('@/shared/viewer/PickViewer', () => ({
  default: ({ mesh, emphasis }: { mesh: { faces: { part?: string }[] }; emphasis?: string | null }) => (
    <div data-testid="viewer" data-emphasis={emphasis ?? ''}>
      {[...new Set(mesh.faces.map((f) => f.part ?? '-'))].join(',')}
    </div>
  ),
}))
vi.mock('@/shared/viewer/GridViewer', () => ({
  GridViewer: ({ items, columns }: { items: { key: string; highlight?: boolean }[]; columns: number }) => (
    <div data-testid="grid" data-columns={columns} data-highlight={items.find((one) => one.highlight)?.key ?? ''}>
      {items.map((one) => one.key).join(',')}
    </div>
  ),
}))

const face = (part?: string) => ({ index: 0, kind: 'plane', center: [0, 0, 0], normal: [0, 0, 1], area: 1, vertices: [], triangles: [], part })
const meshOf = (n: number) => ({ number: n, params: { 두께: n * 2 }, summary: { bbox: { size: [1, 1, n] } }, mesh: { bbox: { min: [0, 0, 0], max: [1, 1, n] }, faces: [face()], edges: [] } })

const STUDY = {
  id: 's1',
  name: '두께 훑기',
  method: 'factorial',
  seed: 1,
  point_count: 3,
  done: 2,
  failed: 1,
  job: { status: 'done', artifacts: [], progress: [] },
  export_dir_windows: '',
  exported_at: null,
  factors: [{ name: '두께', mode: 'list', values: [2, 4, 6] }],
  points: [
    { id: 'a', number: 1, params: { 두께: 2 }, status: 'ok', error: '', metrics: null, step_file: 'points/p0001.step' },
    { id: 'b', number: 2, params: { 두께: 4 }, status: 'ok', error: '', metrics: null, step_file: 'points/p0002.step' },
    { id: 'c', number: 3, params: { 두께: 6 }, status: 'failed', error: '깨짐', metrics: null, step_file: '' },
  ],
} as unknown as DoeStudy

test('표의 줄을 누르면 그 점의 형상을 받아 보고, 체크한 점들은 겹쳐 본다', async () => {
  const asked: string[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = String(input)
    asked.push(url)
    const n = Number(url.match(/points\/(\d+)\/mesh/)?.[1] ?? 0)
    return new Response(JSON.stringify(meshOf(n)), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(
    <MemoryRouter>
      <DoeStudyView study={STUDY} onReload={() => {}} />
    </MemoryRouter>,
  )
  // 처음엔 아무것도 안 받는다 — 점이 수백이라 고른 것만. 하나씩 볼 때는 표에 체크가 없다.
  expect(screen.getByText('표에서 점을 누르세요.')).toBeInTheDocument()
  expect(asked.filter((u) => u.includes('/mesh'))).toHaveLength(0)
  expect(screen.queryByLabelText('p0001 고르기')).toBeNull()

  fireEvent.click(screen.getByText('p0002'))
  await waitFor(() => expect(screen.getByTestId('viewer')).toBeInTheDocument())
  expect(asked.filter((u) => u.includes('/mesh'))).toEqual(['/api/doe/s1/points/2/mesh'])
  expect(screen.getByText('2 / 2')).toBeInTheDocument()
  // ▶ 는 만들어진 점만 돈다 — 실패한 p0003 을 건너 p0001 로.
  fireEvent.click(screen.getByRole('button', { name: '다음 점' }))
  await waitFor(() => expect(asked.filter((u) => u.includes('/mesh'))).toEqual(['/api/doe/s1/points/2/mesh', '/api/doe/s1/points/1/mesh']))
  expect(screen.getByText('1 / 2')).toBeInTheDocument()
  // 실패한 점은 누를 수 없다.
  fireEvent.click(screen.getByText('p0003'))
  expect(asked.filter((u) => u.includes('/mesh'))).toHaveLength(2)

  // 겹쳐 보기 — 체크한 점들이 한 뷰어에 점 이름표로 들어간다. 받은 것은 다시 안 받는다.
  fireEvent.click(screen.getByRole('button', { name: '겹쳐 보기' }))
  fireEvent.click(screen.getByLabelText('p0001 고르기'))
  fireEvent.click(screen.getByLabelText('p0002 고르기'))
  await waitFor(() => expect(screen.getByTestId('viewer').textContent).toBe('p0001,p0002'))
  expect(asked.filter((u) => u.includes('/mesh'))).toEqual(['/api/doe/s1/points/2/mesh', '/api/doe/s1/points/1/mesh'])
  // 줄을 누르면(체크 말고) 그 점만 또렷하다. 다시 누르면 푼다. (범례에도 이름이 있어 표의 칸을 짚는다.)
  const rowOf = (label: string) => screen.getAllByText(label).find((el) => el.closest('tr'))!
  fireEvent.click(rowOf('p0002'))
  expect(screen.getByTestId('viewer').getAttribute('data-emphasis')).toBe('p0002')
  fireEvent.click(rowOf('p0002'))
  expect(screen.getByTestId('viewer').getAttribute('data-emphasis')).toBe('')
  // 나란히 — 한 격자 뷰어에 칸마다. 둘이면 2열. 누른 줄의 칸이 도드라진다.
  fireEvent.click(screen.getByRole('button', { name: '나란히' }))
  await waitFor(() => expect(screen.getByTestId('grid').textContent).toBe('p0001,p0002'))
  expect(screen.getByTestId('grid').getAttribute('data-columns')).toBe('2')
  fireEvent.click(rowOf('p0001'))
  expect(screen.getByTestId('grid').getAttribute('data-highlight')).toBe('p0001')

  // 전체 선택은 만들어진 점만 — 실패한 p0003 은 빠진다. 풀면 비운다.
  fireEvent.click(screen.getByLabelText('p0001 고르기')) // 하나 풀고
  fireEvent.click(screen.getByLabelText('전체 선택'))
  expect((screen.getByLabelText('p0001 고르기') as HTMLInputElement).checked).toBe(true)
  expect(screen.getByText('전체 선택 (2)')).toBeInTheDocument()
  fireEvent.click(screen.getByLabelText('전체 선택'))
  expect((screen.getByLabelText('p0002 고르기') as HTMLInputElement).checked).toBe(false)
})

test('격자 열 수는 정사각형에 가깝게 늘다가 넷에서 멈춘다', async () => {
  const { gridColumns } = await import('@/modules/doe/PointsGallery')
  expect([1, 2, 3, 4, 5, 6, 7, 9, 10, 12, 13, 16, 17, 20, 24].map(gridColumns)).toEqual([1, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4])
})

test('메시를 합치면 면마다 어느 점인지 붙고 번호가 이어진다', () => {
  const merged = mergeMeshes([
    { label: 'p0001', mesh: { bbox: { min: [0, 0, 0], max: [1, 1, 1] }, faces: [face(), face()], edges: [] } },
    { label: 'p0002', mesh: { bbox: { min: [-1, 0, 0], max: [2, 1, 3] }, faces: [face()], edges: [] } },
  ])
  expect(merged.faces.map((f) => [f.index, f.part])).toEqual([
    [0, 'p0001'],
    [1, 'p0001'],
    [2, 'p0002'],
  ])
  expect(merged.bbox).toEqual({ min: [-1, 0, 0], max: [2, 1, 3] })
})

test('고른 점이 상한을 넘으면 쪽으로 넘겨 가며 다 본다', async () => {
  const many = {
    ...STUDY,
    point_count: 30,
    done: 30,
    failed: 0,
    points: Array.from({ length: 30 }, (_, i) => ({ id: `p${i}`, number: i + 1, params: { 두께: i }, status: 'ok', error: '', metrics: null, step_file: `points/p${i}.step` })),
  } as unknown as DoeStudy
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const n = Number(String(input).match(/points\/(\d+)\/mesh/)?.[1] ?? 0)
    return new Response(JSON.stringify(meshOf(n)), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(
    <MemoryRouter>
      <DoeStudyView study={many} onReload={() => {}} />
    </MemoryRouter>,
  )
  fireEvent.click(screen.getByRole('button', { name: '나란히' }))
  fireEvent.click(screen.getByLabelText('전체 선택'))
  // 24씩 — 첫 쪽은 1–24, 4열.
  await waitFor(() => expect(screen.getByTestId('grid').textContent!.split(',')).toHaveLength(24))
  expect(screen.getByText('1–24 / 30')).toBeInTheDocument()
  expect(screen.getByTestId('grid').getAttribute('data-columns')).toBe('4')
  fireEvent.click(screen.getByRole('button', { name: '다음 쪽' }))
  await waitFor(() => expect(screen.getByTestId('grid').textContent!.split(',')).toHaveLength(6))
  expect(screen.getByText('25–30 / 30')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '다음 쪽' })).toBeDisabled()
  // 목록에서 첫 쪽의 점을 짚으면 그 쪽으로 돌아간다.
  fireEvent.click(screen.getAllByText('p0003').find((el) => el.closest('tr'))!)
  await waitFor(() => expect(screen.getByText('1–24 / 30')).toBeInTheDocument())
  expect(screen.getByTestId('grid').getAttribute('data-highlight')).toBe('p0003')
})
