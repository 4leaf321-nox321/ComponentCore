import { FOLLOW_JOB, solverOptions } from '@/modules/conditions/capabilities'

test('대상 솔버 — 비움 다음에 능력표의 솔버, 판이 있으면 함께', () => {
  expect(solverOptions([{ solver: 'calculix', version: null }, { solver: 'ansys', version: '2025 R2' }])).toEqual([
    { key: '', label: FOLLOW_JOB },
    { key: 'calculix', label: 'CalculiX' },
    { key: 'ansys', label: 'Ansys 2025 R2' },
  ])
})

test('능력표를 받은 적이 없으면 아는 둘을 보인다', () => {
  expect(solverOptions(null).map((one) => one.key)).toEqual(['', 'calculix', 'ansys'])
})

test('지금 값이 능력표에 없으면 지우지 않고 「능력표에 없음」 을 붙여 남긴다', () => {
  expect(solverOptions([{ solver: 'calculix' }], 'ansys').at(-1)).toEqual({ key: 'ansys', label: 'ansys (능력표에 없음)' })
  // 받은 적이 없으면 「없음」 이라 말할 근거가 없다 — 이름만.
  expect(solverOptions(null, 'abaqus').at(-1)).toEqual({ key: 'abaqus', label: 'abaqus' })
  expect(solverOptions([{ solver: 'calculix' }], 'calculix')).toHaveLength(2)
})
