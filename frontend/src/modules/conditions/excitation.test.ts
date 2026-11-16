import { cellOf, pasteRows, psdGrms } from '@/modules/conditions/excitation'

test('엑셀 · CSV 에서 복사한 두 열을 행으로 읽고, 머리글 줄은 건너뛴다', () => {
  expect(pasteRows('Hz\tg²/Hz\n20\t0.01\n80\t0.04\r\n2000\t0.007\n')).toEqual([
    [20, 0.01],
    [80, 0.04],
    [2000, 0.007],
  ])
  expect(pasteRows('20,0.01\n80, 0.04\n350;0.04\n2000 0.007')).toEqual([
    [20, 0.01],
    [80, 0.04],
    [350, 0.04],
    [2000, 0.007],
  ])
  // 셋째 칸(메모)은 버린다.
  expect(pasteRows('20\t0.01\t오르막')).toEqual([[20, 0.01]])
})

test('칸은 수 · =식 그대로, 빈칸은 빈칸', () => {
  expect(cellOf(' 12.5 ')).toBe(12.5)
  expect(cellOf('=배율')).toBe('=배율')
  expect(cellOf('')).toBe('')
})

test('PSD 의 실효값은 로그-로그 면적의 제곱근이다 — 서버(`psd_grms`)와 같은 예', () => {
  expect(psdGrms([[20, 0.04], [2000, 0.04]])).toBeCloseTo(Math.sqrt(0.04 * 1980), 6)
  // 기울기 -1 구간.
  expect(psdGrms([[100, 0.1], [1000, 0.01]])).toBeCloseTo(Math.sqrt(0.1 * 100 * Math.log(10)), 6)
  expect(psdGrms([[20, '=a'], [2000, 0.04]])).toBeNull()
  expect(psdGrms([[20, 0.04]])).toBeNull()
})
