import { cellOf, G_SQUARED, pasteRows, psdGrms, toG2 } from '@/modules/conditions/excitation'

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

test('(m/s²)²/Hz 표를 g²/Hz 로 나눈다 — 받는 쪽은 g²/Hz 만 받는다', () => {
  expect(G_SQUARED).toBeCloseTo(96.17, 2)
  // IEC 60068-2-64 꼴로 적힌 3.85 (m/s²)²/Hz ≈ 0.04 g²/Hz. 식 · 빈칸은 그대로.
  expect(toG2([[20, 3.8466], [80, '=a'], [350, '']])).toEqual([
    [20, 0.0399978],
    [80, '=a'],
    [350, ''],
  ])
  // 단위를 바꿔도 Grms 는 g 로 9.80665 배 작아질 뿐이다.
  const ms2: [number, number][] = [[20, 3.85], [2000, 3.85]]
  expect(psdGrms(toG2(ms2))! * 9.80665).toBeCloseTo(psdGrms(ms2)!, 3)
})
