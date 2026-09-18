import { fireEvent, render, screen } from '@testing-library/react'

import { SketchCanvas } from '@/modules/cad/SketchCanvas'
import type { SketchShape } from '@/modules/cad/SketchCanvas'

function mockBox(element: Element) {
  element.getBoundingClientRect = () =>
    ({ left: 0, top: 0, width: 560, height: 400, right: 560, bottom: 400, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect
}

test('도구를 고르고 캔버스를 누르면 도형이 놓인다 — 격자에 맞춰', () => {
  const shapes: SketchShape[] = [{ type: 'rect', width: 40, height: 30, at: [0, 0], rotation: 0, mode: 'add' }]
  const onChange = vi.fn()
  const { container } = render(<SketchCanvas shapes={shapes} onChange={onChange} />)
  const svg = container.querySelector('svg')!
  mockBox(svg)

  fireEvent.click(screen.getByRole('button', { name: '+ 원' }))
  // 가운데(280, 200)가 원점. 오른쪽 위로 조금 — 스냅으로 정수 mm 가 된다.
  fireEvent.pointerDown(svg, { clientX: 300, clientY: 180, shiftKey: false })

  expect(onChange).toHaveBeenCalledTimes(1)
  const next = onChange.mock.calls[0][0] as SketchShape[]
  expect(next).toHaveLength(2)
  expect(next[1].type).toBe('circle')
  const [x, y] = next[1].at as number[]
  expect(Number.isInteger(x) && Number.isInteger(y)).toBe(true)
  expect(x).toBeGreaterThan(0)
  expect(y).toBeGreaterThan(0) // 화면 위쪽 = +Y
})

test('도형을 누르면 치수 폼이 뜨고 고치면 반영된다', () => {
  const shapes: SketchShape[] = [{ type: 'circle', radius: 5, at: [0, 0], rotation: 0, mode: 'add' }]
  const onChange = vi.fn()
  const { container } = render(<SketchCanvas shapes={shapes} onChange={onChange} />)
  mockBox(container.querySelector('svg')!)
  const circle = container.querySelector('circle')!
  fireEvent.pointerDown(circle, { clientX: 280, clientY: 200 })
  const radius = screen.getByLabelText('반지름') as HTMLInputElement
  fireEvent.change(radius, { target: { value: '8' } })
  const next = onChange.mock.calls.at(-1)![0] as SketchShape[]
  expect(next[0].radius).toBe(8)
})

test('선(두께) — 점을 찍고 「선 끝내기」 하면 중심선과 폭을 가진 도형이 된다', () => {
  const onChange = vi.fn()
  const { container } = render(<SketchCanvas shapes={[]} onChange={onChange} />)
  const svg = container.querySelector('svg')!
  mockBox(svg)
  fireEvent.click(screen.getByRole('button', { name: '+ 선 (두께)' }))
  fireEvent.pointerDown(svg, { clientX: 280, clientY: 200 })
  fireEvent.pointerDown(svg, { clientX: 380, clientY: 200 })
  fireEvent.click(screen.getByRole('button', { name: /선 끝내기/ }))
  const next = onChange.mock.calls.at(-1)![0] as SketchShape[]
  expect(next).toHaveLength(1)
  expect(next[0].type).toBe('path')
  expect(next[0].width).toBe(3)
  expect((next[0].segments as { to: number[] }[])).toHaveLength(1)
})

test('삼각형 · 호(반지름 · 접선)를 캔버스가 서버와 같게 그린다', () => {
  const shapes: SketchShape[] = [
    { type: 'triangle', a: 30, b: 40, C: 90, at: [0, 0], rotation: 0, mode: 'add' },
    {
      type: 'polyline',
      start: [0, 0],
      segments: [{ to: [40, 0] }, { to: [40, 30], radius: 25 }, { to: [0, 30] }],
      at: [0, 0],
      rotation: 0,
      mode: 'add',
    },
  ]
  const { container } = render(<SketchCanvas shapes={shapes} onChange={() => {}} />)
  // 삼각형 — 무게중심이 원점, 변 길이 30 · 40 · 50 (서버 Triangle 과 같은 배치).
  const points = container.querySelector('polygon')!.getAttribute('points')!.split(' ').map((p) => p.split(',').map(Number))
  const sides = points.map(([x, y], i) => {
    const [nx, ny] = points[(i + 1) % 3]
    return Math.round(Math.hypot(nx - x, ny - y))
  })
  expect(sides.sort((p, q) => p - q)).toEqual([30, 40, 50])
  expect(Math.abs(points.reduce((sum, [x]) => sum + x, 0))).toBeLessThan(0.01)
  // 반지름 호는 A 명령으로 그려진다(직선 L 이 아니라).
  expect(container.querySelector('path')!.getAttribute('d')).toMatch(/A /)
})
