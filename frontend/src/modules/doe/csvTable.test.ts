import { formatTable, parseTable } from '@/modules/doe/csvTable'

test('엑셀에서 복사한 탭 표와 CSV 를 다 읽고, 번호 열은 버린다', () => {
  const tab = parseTable('point\t두께\t길이\n1\t4\t80\n2\t6.333\t90\n')
  expect(tab.columns).toEqual(['두께', '길이'])
  expect(tab.rows).toEqual([
    { 두께: '4', 길이: '80' },
    { 두께: '6.333', 길이: '90' },
  ])
  const csv = parseTable('﻿두께,재료\n4,"SECC, 도금"\n5\n')
  expect(csv.rows).toEqual([{ 두께: '4', 재료: 'SECC, 도금' }])
  expect(csv.problems[0]).toMatch(/3 번째 줄은 칸이 1 개라 버렸습니다/)
  expect(parseTable('').rows).toEqual([])
})

test('표를 CSV 로 되돌리면 다시 같은 표로 읽힌다', () => {
  const text = formatTable(['두께', '재료'], [{ 두께: 4, 재료: 'SECC, 도금' }])
  expect(parseTable(text).rows).toEqual([{ 두께: '4', 재료: 'SECC, 도금' }])
})
