import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import type { Part } from '@/modules/parts/api'
import { StandardCard } from '@/modules/parts/StandardCard'

const PART = {
  id: 'p1',
  name: '받침 Ø16',
  description: '',
  owner_id: 'u1',
  owner_name: '김',
  work_id: null,
  current_version: 2,
  version_count: 2,
  current: null,
  jig_count: 0,
  folder: '',
  standard: null,
  created_at: '2026-10-04T00:00:00Z',
  updated_at: '2026-10-04T00:00:00Z',
} as unknown as Part

function serve(status = 200) {
  const sent: { url: string; method: string; body: Record<string, unknown> | null }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    sent.push({ url: String(input), method: init?.method ?? 'GET', body: init?.body ? JSON.parse(String(init.body)) : null })
    const body =
      status === 200
        ? { ...PART, standard: { kind: 'support', part_no: 'SUP-16', version: 2 } }
        : { error: { code: 'CCR-PARTS-0010', message: '규격 사양이 형상과 맞지 않습니다.', details: { problems: ['바닥이 z=0 이 아닙니다(z=5.00). 바닥을 원점 높이에 맞추십시오.'] } } }
    return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
  })
  return sent
}

test('관리자는 규격 사양을 등록한다 — 종류의 칸과 높이 변수 범위를 함께', async () => {
  const sent = serve()
  const changed = vi.fn()
  render(<StandardCard part={PART} admin onChanged={changed} />)
  fireEvent.click(screen.getByRole('button', { name: '규격 사양 등록' }))
  expect(screen.getByLabelText('사용할 버전')).toHaveValue(2) // 지금 버전이 기본
  fireEvent.change(screen.getByLabelText('품번'), { target: { value: 'SUP-16' } })
  fireEvent.change(screen.getByLabelText('윗면 지름 (mm)'), { target: { value: '16' } })
  fireEvent.change(screen.getByLabelText('높이 (mm)'), { target: { value: '25' } })
  fireEvent.change(screen.getByLabelText('높이 변수 (선택)'), { target: { value: '높이' } })
  fireEvent.change(screen.getByLabelText('최소'), { target: { value: '10' } })
  fireEvent.change(screen.getByLabelText('최대'), { target: { value: '60' } })
  fireEvent.click(screen.getByRole('button', { name: '저장' }))
  await waitFor(() => expect(changed).toHaveBeenCalled())
  const put = sent.find((one) => one.method === 'PUT')!
  expect(put.url).toMatch(/\/parts\/p1\/standard$/)
  expect(put.body).toMatchObject({ kind: 'support', part_no: 'SUP-16', version: 2, top_diameter: 16, height: 25, height_param: '높이', height_min: 10, height_max: 60 })
})

test('형상이 기준을 어기면 무엇을 고칠지 보인다', async () => {
  serve(400)
  render(<StandardCard part={PART} admin onChanged={() => {}} />)
  fireEvent.click(screen.getByRole('button', { name: '규격 사양 등록' }))
  fireEvent.change(screen.getByLabelText('품번'), { target: { value: 'SUP-16' } })
  fireEvent.click(screen.getByRole('button', { name: '저장' }))
  expect(await screen.findByText(/바닥이 z=0 이 아닙니다/)).toBeInTheDocument()
})

test('일반 사용자는 사양이 있을 때만 보고, 고치는 단추가 없다', () => {
  const { unmount } = render(<StandardCard part={PART} admin={false} onChanged={() => {}} />)
  expect(screen.queryByText('규격 사양')).toBeNull()
  unmount()
  render(
    <StandardCard
      part={{ ...PART, standard: { kind: 'clamp', part_no: 'TC-60', version: 1, reach: 60, pad_height: 30, pad_diameter: 10, base_length: 40, base_width: 30 } }}
      admin={false}
      onChanged={() => {}}
    />,
  )
  expect(screen.getByText('TC-60')).toBeInTheDocument()
  expect(screen.getByText(/도달 거리 60 · 누르는 높이 30/)).toBeInTheDocument()
  expect(screen.getByText(/고정 나사 자리 없음/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /규격 사양/ })).toBeNull()
})

const CLAMP = { kind: 'clamp', part_no: 'TC-60', version: 1, reach: 60, pad_height: 30, pad_diameter: 10, base_length: 40, base_width: 30 } as const

test('클램프는 고정 나사와 구멍 자리를 적는다 — 있던 자리가 글로 채워지고 목록으로 나간다', async () => {
  const sent = serve()
  const changed = vi.fn()
  render(<StandardCard part={{ ...PART, standard: { ...CLAMP, mount_thread: 'M5', mount_holes: [[-15, -10], [15, 10]] } }} admin onChanged={changed} />)
  expect(screen.getByText(/고정 나사 M5 × 2/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '규격 사양 편집' }))
  expect(screen.getByLabelText('고정 나사')).toHaveValue('M5')
  expect(screen.getByLabelText(/고정 구멍 자리/)).toHaveValue('-15,-10; 15,10')
  fireEvent.change(screen.getByLabelText('고정 나사'), { target: { value: 'M6' } })
  fireEvent.change(screen.getByLabelText(/고정 구멍 자리/), { target: { value: '-15,-10; -15, 10; 15,-10; 15,10' } })
  fireEvent.click(screen.getByRole('button', { name: '저장' }))
  await waitFor(() => expect(changed).toHaveBeenCalled())
  const put = sent.find((one) => one.method === 'PUT')!
  expect(put.body).toMatchObject({
    kind: 'clamp',
    mount_thread: 'M6',
    mount_holes: [
      [-15, -10],
      [-15, 10],
      [15, -10],
      [15, 10],
    ],
  })
})

test('구멍 자리를 잘못 적으면 보내지 않고 적는 법을 말한다', async () => {
  const sent = serve()
  render(<StandardCard part={{ ...PART, standard: CLAMP }} admin onChanged={() => {}} />)
  fireEvent.click(screen.getByRole('button', { name: '규격 사양 편집' }))
  fireEvent.change(screen.getByLabelText(/고정 구멍 자리/), { target: { value: '-15 -10' } })
  fireEvent.click(screen.getByRole('button', { name: '저장' }))
  expect(await screen.findByText(/처럼 적으십시오/)).toBeInTheDocument()
  expect(sent.some((one) => one.method === 'PUT')).toBe(false)
})
