import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'

import { withSetting } from '@/modules/conditions/api'
import type { Body, BodySetting, ConditionsSchema, MaterialItem } from '@/modules/conditions/api'
import { PartSettingsDialog } from '@/modules/conditions/PartSettingsDialog'

const SCHEMA: ConditionsSchema['body_settings'] = {
  label: '파트별 설정',
  intro: '파트마다 지정합니다.',
  fields: {
    behavior: { title: '거동', enum: ['deformable', 'rigid'], labels: { deformable: '변형체', rigid: '강체' } },
    representation: { title: '표현', enum: ['solid', 'shell'], labels: { solid: '솔리드', shell: '쉘' } },
    thickness: { title: '두께(mm)' },
    suppressed: { title: '해석 제외' },
  },
  mesh_fields: {
    element_size: { title: '요소 크기', unit: 'mm' },
    method: { title: '요소 형상', enum: ['automatic', 'tetrahedrons'], labels: { automatic: '자동', tetrahedrons: '사면체' } },
    order: { title: '요소 차수', enum: ['program_controlled', 'quadratic'], labels: { program_controlled: '프로그램 제어', quadratic: '2차(정확)' } },
  },
}

const STEEL: MaterialItem = { apply_to: [], ref: { name: 'SPCC' }, payload: {} }

/** 표를 진짜 화면처럼 — 바뀐 것이 다시 표로 돌아온다. 마지막 값을 밖에서 본다. */
const PARTS: Body[] = [
  { name: '지그판', volume: 30000 },
  { name: '부품', volume: 7200 },
]

function Harness({
  seen,
  bodies = PARTS,
}: {
  seen: { settings: BodySetting[]; materials: MaterialItem[] }
  bodies?: Body[]
}) {
  const [settings, setSettings] = useState<BodySetting[]>([])
  const [materials, setMaterials] = useState<MaterialItem[]>([STEEL])
  seen.settings = settings
  seen.materials = materials
  return (
    <PartSettingsDialog
      open
      onClose={() => {}}
      bodies={bodies}
      materials={materials}
      settings={settings}
      schema={SCHEMA}
      onMaterialsChange={setMaterials}
      onSettingsChange={setSettings}
      onPickMaterials={() => {}}
    />
  )
}

test('파트마다 한 줄 — 거동 · 표현 · 해석 제외 · 메시를 고치고, 모든 파트 줄로 한꺼번에', () => {
  const seen = { settings: [] as BodySetting[], materials: [] as MaterialItem[] }
  render(<Harness seen={seen} />)

  // 물성 — 파트 하나에 하나(트리와 같은 규칙).
  fireEvent.change(screen.getByLabelText('지그판 물성'), { target: { value: '0' } })
  expect(seen.materials[0].apply_to).toEqual(['지그판'])

  // 강체로 두면 표현은 솔리드로 잠긴다(서버도 강체 + 쉘을 막는다).
  fireEvent.change(screen.getByLabelText('부품 표현'), { target: { value: 'shell' } })
  fireEvent.change(screen.getByLabelText('지그판 거동'), { target: { value: 'rigid' } })
  expect(screen.getByLabelText('지그판 표현')).toBeDisabled()
  expect(screen.getByText(/설계점마다 중간면 STEP/)).toBeInTheDocument()

  // 모든 파트 줄 — 요소 크기를 한꺼번에. 값이 갈리는 열은 「혼합」.
  fireEvent.change(screen.getByLabelText('모든 파트 요소 크기'), { target: { value: '2' } })
  expect(Object.fromEntries(seen.settings.map((one) => [one.name, one.mesh?.element_size]))).toEqual({ 지그판: 2, 부품: 2 })
  expect(screen.getByLabelText('모든 파트 거동')).toHaveValue('__mixed__')
  fireEvent.change(screen.getByLabelText('모든 파트 요소 차수'), { target: { value: 'quadratic' } })
  expect(seen.settings.every((one) => one.mesh?.order === 'quadratic')).toBe(true)

  // 해석 제외 — 그 줄의 나머지 칸은 잠긴다.
  fireEvent.click(screen.getByLabelText('부품 해석 제외'))
  expect(screen.getByLabelText('부품 거동')).toBeDisabled()
  expect(screen.getByLabelText('부품 요소 크기')).toBeDisabled()
  expect(seen.settings.find((one) => one.name === '부품')?.suppressed).toBe(true)
})

test('기본값으로 돌아온 파트는 저장 목록에서 빠진다', () => {
  let settings = withSetting([], '부품', { behavior: 'rigid' })
  expect(settings).toHaveLength(1)
  settings = withSetting(settings, '부품', { behavior: 'deformable' })
  expect(settings).toEqual([])
  // 강체로 바꾸면 쉘은 솔리드로 다듬는다.
  settings = withSetting(withSetting([], '판', { representation: 'shell' }), '판', { behavior: 'rigid' })
  expect(settings[0]).toMatchObject({ behavior: 'rigid', representation: 'solid' })
})

test('고쳤다 되돌리면 저장 목록이 처음과 같다 — 줄의 자리를 지킨다', () => {
  const before = withSetting(withSetting([], '판', { behavior: 'rigid' }), '블록', { suppressed: true })
  const changed = withSetting(before, '판', { mesh: { element_size: 3 } })
  expect(withSetting(changed, '판', { mesh: { element_size: null } })).toEqual(before)
})

test('시트 파트(셸 모델)는 변형체 쉘로 고정되고 두께만 적는다 — 솔리드는 쉘이어도 두께를 형상에서', () => {
  const seen = { settings: [] as BodySetting[], materials: [] as MaterialItem[] }
  render(
    <Harness
      seen={seen}
      bodies={[
        { name: '덮개', kind: 'sheet', area: 1218, volume: 0 },
        { name: '받침', kind: 'solid', volume: 2400 },
      ]}
    />,
  )
  // 부피 0 대신 넓이로, 무엇을 해야 중간면이 나가는지 함께.
  expect(screen.getByText(/시트\(셸 모델\) · 넓이 1,218 mm²/)).toBeInTheDocument()
  expect(screen.getByText(/두께를 잴 수 없으니 입력해야 중간면이 생성됩니다/)).toBeInTheDocument()
  expect(screen.getByLabelText('덮개 두께(mm)')).toHaveAttribute('placeholder', '필수')
  // 시트는 솔리드 · 강체로 고를 수 없다 — SimEngBay 가 작업을 막는 조합이다(2026-10-16).
  expect(screen.getByLabelText('덮개 표현')).toHaveValue('shell')
  expect(screen.getByLabelText('덮개 표현')).toBeDisabled()
  expect(screen.getByLabelText('덮개 거동')).toBeDisabled()

  fireEvent.change(screen.getByLabelText('덮개 두께(mm)'), { target: { value: '1.2' } })
  expect(seen.settings.find((one) => one.name === '덮개')).toMatchObject({
    behavior: 'deformable',
    representation: 'shell',
    thickness: 1.2,
  })

  // 솔리드를 쉘로 풀어도 두께 칸은 닫혀 있다 — 형상에서 잰다(적은 값은 쓰이지 않았다).
  fireEvent.change(screen.getByLabelText('받침 표현'), { target: { value: 'shell' } })
  expect(screen.getByLabelText('받침 두께(mm)')).toBeDisabled()
  expect(screen.getByLabelText('받침 두께(mm)')).toHaveAttribute('placeholder', '형상에서')

  // 「모든 파트」 에서 솔리드 · 강체를 골라도 시트는 쉘로 남고 두께도 그대로다.
  fireEvent.change(screen.getByLabelText('모든 파트 표현'), { target: { value: 'solid' } })
  fireEvent.change(screen.getByLabelText('모든 파트 거동'), { target: { value: 'rigid' } })
  expect(seen.settings.find((one) => one.name === '덮개')).toMatchObject({
    behavior: 'deformable',
    representation: 'shell',
    thickness: 1.2,
  })
  expect(seen.settings.find((one) => one.name === '받침')).toMatchObject({ behavior: 'rigid', representation: 'solid' })
})
