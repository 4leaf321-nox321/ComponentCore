import { fireEvent, render, screen } from '@testing-library/react'

import { CurvePlot } from '@/modules/conditions/CurvePlot'

const tickLabels = (container: HTMLElement) => [...container.querySelectorAll('text')].map((one) => one.textContent)

test('로그-로그는 두 축이 십진 눈금 — PSD 가 규격의 기울기대로 직선이 된다', () => {
  const { container } = render(
    <CurvePlot title="가속도 PSD" points={[[20, 0.01], [80, 0.04], [350, 0.04], [2000, 0.007]]} interpolation="loglog" xLabel="주파수 (Hz)" yLabel="PSD (g²/Hz)" />,
  )
  const plot = screen.getByRole('img', { name: /가속도 PSD 그래프 — 4점, 가로 20 ~ 2000, 값 0.007 ~ 0.04, 로그-로그 눈금/ })
  expect(plot).toBeInTheDocument()
  const labels = tickLabels(container)
  for (const tick of ['10', '100', '1000', '10000', '0.001', '0.01', '0.1']) expect(labels).toContain(tick)
  // 선 하나와 점 넷.
  expect(container.querySelectorAll('path')).toHaveLength(1)
  expect(container.querySelectorAll('circle')).toHaveLength(4)
})

test('선형은 세로축이 0 을 품고, 계단은 다음 점까지 값을 유지한다', () => {
  const { container } = render(<CurvePlot title="배율" points={[[0, 2], [10, 4], [20, 3]]} interpolation="step" xLabel="시간 (s)" yLabel="값" />)
  expect(tickLabels(container)).toContain('0')
  // 계단 — H(가로) 다음 V(세로).
  expect(container.querySelector('path')?.getAttribute('d')).toMatch(/^M[\d.]+,[\d.]+H[\d.]+V[\d.]+H[\d.]+V[\d.]+$/)
})

test('식인 점은 그리지 않고 말한다 — 두 점이 안 되면 그래프 대신 안내', () => {
  const { rerender } = render(<CurvePlot title="배율" points={[[10, 1], [20, '=a'], [30, 2]]} xLabel="주파수 (Hz)" yLabel="배율" />)
  expect(screen.getByText('1개 점은 식이라 그리지 않았습니다.')).toBeInTheDocument()
  rerender(<CurvePlot title="배율" points={[[10, 1]]} scale="=k" xLabel="주파수 (Hz)" yLabel="배율" />)
  expect(screen.queryByRole('img')).toBeNull()
  expect(screen.getByText(/점이 두 개 이상 있으면 그래프가 표시됩니다\. 배율이 식이라 모양만 표시합니다\./)).toBeInTheDocument()
  // 로그 축에 0 이하는 못 그린다.
  rerender(<CurvePlot title="PSD" points={[[10, 0], [20, 1], [40, 2]]} interpolation="loglog" xLabel="주파수 (Hz)" yLabel="PSD" />)
  expect(screen.getByText('1개 점은 식이거나 0 이하라 그리지 않았습니다.')).toBeInTheDocument()
})

test('초점을 두고 ← → 로 점을 옮기면 값이 뜬다(가리킬 때와 같다) — 배율을 곱한 값', () => {
  render(<CurvePlot title="배율" points={[[10, 1], [100, 0.5]]} scale={2} xLabel="주파수 (Hz)" yLabel="배율" />)
  const plot = screen.getByRole('img')
  fireEvent.keyDown(plot, { key: 'ArrowRight' })
  expect(screen.getByRole('status')).toHaveTextContent('2 배율 · 10 주파수 (Hz)')
  fireEvent.keyDown(plot, { key: 'ArrowRight' })
  expect(screen.getByRole('status')).toHaveTextContent('1 배율 · 100 주파수 (Hz)')
  fireEvent.blur(plot)
  expect(screen.queryByRole('status')).toBeNull()
})
