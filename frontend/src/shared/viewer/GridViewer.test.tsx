import { render } from '@testing-library/react'

// three 는 WebGL 이 필요하다 — 렌더러만 빈 껍데기로 바꾸고 나머지(장면 · 카메라)는 진짜를 쓴다.
vi.mock('three', async () => {
  const real = await vi.importActual<typeof import('three')>('three')
  class FakeRenderer {
    domElement = document.createElement('canvas')
    setPixelRatio() {}
    setScissorTest() {}
    setSize() {}
    setViewport() {}
    setScissor() {}
    render() {}
    dispose() {}
  }
  return { ...real, WebGLRenderer: FakeRenderer }
})

import { GridViewer } from '@/shared/viewer/GridViewer'

const mesh = { bbox: { min: [0, 0, 0], max: [1, 1, 1] }, faces: [], edges: [] }

test('도드라진 칸이 바뀌면 그 칸으로 스크롤한다', () => {
  const scrolled: string[] = []
  Element.prototype.scrollIntoView = function () {
    scrolled.push((this as HTMLElement).getAttribute('aria-current') ?? 'none')
  }
  const items = (highlight: string) => ['a', 'b', 'c'].map((key) => ({ key, label: key, mesh, highlight: key === highlight }))
  const { rerender } = render(<GridViewer items={items('a')} columns={2} />)
  expect(scrolled).toEqual(['true'])
  rerender(<GridViewer items={items('c')} columns={2} />)
  expect(scrolled).toEqual(['true', 'true'])
  rerender(<GridViewer items={items('c')} columns={2} />) // 같은 칸이면 다시 안 움직인다
  expect(scrolled).toHaveLength(2)
})
