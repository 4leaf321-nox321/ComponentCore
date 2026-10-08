import { fireEvent, render, screen } from '@testing-library/react'

import { BomLine, bomCsv } from '@/modules/jigs/BomLine'

const ROWS = [
  { part_no: 'TC-60', name: '토글 클램프 60', kind: 'clamp', count: 2 },
  { part_no: 'ISO 4762 M5', name: '육각 구멍붙이 볼트 (클램프 고정)', kind: 'screw', count: 8 },
  { part_no: 'SUP-16', name: '받침 "Ø16", 강', kind: 'support', count: 4 },
]

test('부품표 CSV 는 품번 · 이름 · 종류 · 수량이고, 엑셀이 한글을 읽게 BOM 을 앞에 둔다', () => {
  const csv = bomCsv(ROWS)
  expect(csv.startsWith('﻿')).toBe(true)
  expect(csv.slice(1).split('\r\n')).toEqual([
    '품번,이름,종류,수량',
    'TC-60,토글 클램프 60,토글 클램프,2',
    'ISO 4762 M5,육각 구멍붙이 볼트 (클램프 고정),볼트,8',
    'SUP-16,"받침 ""Ø16"", 강",받침,4', // 쉼표 · 따옴표가 든 칸은 묶는다
    '',
  ])
})

test('부품표가 있으면 한 줄과 다운로드 단추, 없으면 아무것도 없다', async () => {
  const created = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:bom')
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  let saved = ''
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    saved = this.download
  })
  const { unmount } = render(<BomLine rows={ROWS.slice(0, 1)} name="브래킷/지그" />)
  expect(screen.getByText('규격 부품: TC-60 토글 클램프 60 × 2')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '부품표 CSV' }))
  expect(created).toHaveBeenCalled()
  expect(saved).toBe('브래킷 지그-부품표.csv')
  const blob = created.mock.calls[0][0] as Blob
  expect(await blob.text()).toContain('TC-60,토글 클램프 60,토글 클램프,2')
  unmount()

  const { container } = render(<BomLine rows={[]} name="x" />)
  expect(container).toBeEmptyDOMElement()
})
