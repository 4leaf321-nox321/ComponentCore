import { fireEvent, render, screen } from '@testing-library/react'

import type { RecipeFrame } from '@/modules/cad/api'
import { FramesDialog } from '@/modules/cad/FramesDialog'

test('도면의 좌표계를 더하고 원점에 **치수 식**을 적는다 — DOE 로 치수가 바뀌면 따라간다', () => {
  let frames: RecipeFrame[] = []
  const { rerender } = render(<FramesDialog open frames={frames} onChange={(next) => (frames = next)} onClose={() => {}} picked={0} onPicked={() => {}} />)

  fireEvent.click(screen.getByRole('button', { name: '좌표계 추가' }))
  expect(frames).toEqual([{ name: '좌표계 1', origin: [0, 0, 0], rotate: [0, 0, 0] }])
  rerender(<FramesDialog open frames={frames} onChange={(next) => (frames = next)} onClose={() => {}} picked={0} onPicked={() => {}} />)

  fireEvent.change(screen.getByLabelText('원점 X'), { target: { value: '=길이/2' } })
  rerender(<FramesDialog open frames={frames} onChange={(next) => (frames = next)} onClose={() => {}} picked={0} onPicked={() => {}} />)
  fireEvent.change(screen.getByLabelText('회전 Y'), { target: { value: '90' } })
  expect(frames[0].origin).toEqual(['=길이/2', 0, 0])
  expect(frames[0].rotate).toEqual([0, 90, 0])
})

test('전역(global)이나 겹치는 이름은 알린다', () => {
  render(<FramesDialog open frames={[{ name: 'global' }]} onChange={() => {}} onClose={() => {}} picked={0} onPicked={() => {}} />)
  expect(screen.getByText(/전역\(global\)의 이름입니다/)).toBeInTheDocument()
})
