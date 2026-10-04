import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'

import type { Mate } from '@/modules/cad/api'
import { describeSelect, MatesPanel } from '@/modules/works/MatesPanel'
import type { MateDraft } from '@/modules/works/MatesPanel'

function Host({ initial = [], onMates }: { initial?: Mate[]; onMates?: (next: Mate[]) => void }) {
  const [mates, setMates] = useState<Mate[]>(initial)
  const [draft, setDraft] = useState<MateDraft | null>(null)
  const [picking, setPicking] = useState<'this' | 'to' | null>(null)
  return (
    <>
      <MatesPanel
        node={{ id: '부품' }}
        earlier={[{ id: '지그', label: '시험 지그' }]}
        mates={mates}
        params={{}}
        onCreateParam={() => {}}
        onChange={(next) => {
          setMates(next)
          onMates?.(next)
        }}
        draft={draft}
        onDraft={setDraft}
        picking={picking}
        onPicking={setPicking}
        placement={mates.length ? { rotation: [], translation: [], mates: mates.length, free_rotation: 1, free_translation: 0 } : null}
      />
      {/* 3D 에서 누른 것을 흉내 — 실제로는 편집기가 서버(mate-pick)의 답을 넣는다. */}
      <button type="button" onClick={() => setDraft((now) => now && { ...now, this: { what: 'faces', role: 'bottom' } })}>
        이것을 눌렀다
      </button>
      <span data-testid="picking">{picking ?? ''}</span>
    </>
  )
}

test('질의를 사람 말로 읽는다', () => {
  expect(describeSelect({ what: 'faces', role: 'bottom' })).toBe('아랫면')
  expect(describeSelect({ what: 'faces', kind: 'cylinder', radius: 4, axis: [0, 0, 1] })).toBe('R4 Z축 원통면')
  expect(describeSelect({ what: 'faces', kind: 'plane', normal: [-1, 0, 0], near: [0, 0, 0], limit: 1 })).toBe('-X 평면 (클릭 위치)')
  expect(describeSelect({ what: 'edges', kind: 'circle', near: [1, 2, 3] })).toBe('원 엣지 (클릭 위치)')
})

test('이것을 3D 에서, 상대를 기준면으로 골라 구속을 더하고 틈을 고친다', () => {
  const onMates = vi.fn()
  render(<Host onMates={onMates} />)
  fireEvent.click(screen.getByRole('button', { name: '+ 구속' }))
  // 더하자마자 「이것」 을 고르는 중 — 3D 에서 면을 누르면 된다.
  expect(screen.getByTestId('picking')).toHaveTextContent('this')
  expect(screen.getByRole('button', { name: '구속 추가' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: '이것을 눌렀다' }))
  fireEvent.change(screen.getByLabelText('상대 기준'), { target: { value: 'XY' } })
  fireEvent.click(screen.getByRole('button', { name: '구속 추가' }))
  expect(onMates).toHaveBeenLastCalledWith([{ type: 'touch', this: { what: 'faces', role: 'bottom' }, to: 'XY' }])
  expect(screen.getByText(/아랫면 → XY 평면/)).toBeInTheDocument()
  expect(screen.getByRole('status')).toHaveTextContent('남은 자유도: 회전 1, 이동 0')

  fireEvent.change(screen.getByLabelText('구속 1 간극'), { target: { value: '2' } })
  fireEvent.blur(screen.getByLabelText('구속 1 간극'))
  expect(onMates).toHaveBeenLastCalledWith([expect.objectContaining({ offset: 2 })])
})

test('동심은 방향을 뒤집을 수 있고, 빼면 사라진다', () => {
  const onMates = vi.fn()
  const holes: Mate = { type: 'concentric', this: { what: 'faces', kind: 'cylinder' }, to: '지그', select: { what: 'faces', kind: 'cylinder', radius: 4 } }
  render(<Host initial={[holes]} onMates={onMates} />)
  expect(screen.getByText(/원통면 → 시험 지그 R4 원통면/)).toBeInTheDocument()
  fireEvent.click(screen.getByLabelText('방향 반전'))
  expect(onMates).toHaveBeenLastCalledWith([{ ...holes, flip: true }])
  fireEvent.click(screen.getByRole('button', { name: '구속 1 제거' }))
  expect(onMates).toHaveBeenLastCalledWith([])
})
