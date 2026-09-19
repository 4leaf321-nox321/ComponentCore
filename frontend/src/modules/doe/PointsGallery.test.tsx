import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import type { DoeStudy } from '@/modules/doe/api'
import { DoeStudyView } from '@/modules/doe/DoeStudyView'
import { mergeMeshes } from '@/modules/doe/PointsGallery'

vi.mock('@/shared/viewer/PickViewer', () => ({
  default: ({ mesh }: { mesh: { faces: { part?: string }[] } }) => <div data-testid="viewer">{[...new Set(mesh.faces.map((f) => f.part ?? '-'))].join(',')}</div>,
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
  // 처음엔 아무것도 안 받는다 — 점이 수백이라 고른 것만.
  expect(screen.getByText('표에서 점을 누르세요.')).toBeInTheDocument()
  expect(asked.filter((u) => u.includes('/mesh'))).toHaveLength(0)

  fireEvent.click(screen.getByText('p0002'))
  await waitFor(() => expect(screen.getByTestId('viewer')).toBeInTheDocument())
  expect(asked.filter((u) => u.includes('/mesh'))).toEqual(['/api/doe/s1/points/2/mesh'])
  // 실패한 점은 누를 수 없다.
  fireEvent.click(screen.getByText('p0003'))
  expect(asked.filter((u) => u.includes('/mesh'))).toHaveLength(1)

  // 겹쳐 보기 — 체크한 점들이 한 뷰어에 점 이름표로 들어간다. 받은 것은 다시 안 받는다.
  fireEvent.click(screen.getByRole('button', { name: '겹쳐 보기' }))
  fireEvent.click(screen.getByLabelText('p0001 고르기'))
  fireEvent.click(screen.getByLabelText('p0002 고르기'))
  await waitFor(() => expect(screen.getByTestId('viewer').textContent).toBe('p0001,p0002'))
  expect(asked.filter((u) => u.includes('/mesh'))).toEqual(['/api/doe/s1/points/2/mesh', '/api/doe/s1/points/1/mesh'])
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
