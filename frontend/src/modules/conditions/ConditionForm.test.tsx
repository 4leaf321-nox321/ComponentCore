import { fireEvent, render, screen, within } from '@testing-library/react'

import type { ConditionItem, CurveItem, GroupSchema } from '@/modules/conditions/api'
import { ConditionForm } from '@/modules/conditions/ConditionForm'

const axis = (title: string, onlyFor = ['displacement', 'remote_displacement']) => ({
  title,
  anyOf: [{ type: 'number' }, { type: 'null' }],
  component: true,
  only_for: onlyFor,
  ...(onlyFor.length === 1 ? { unit: '도' } : { dimension: 'length' }),
})
const cylinder = (title: string, description: string) => ({ title, description, enum: ['fixed', 'free'], default: 'fixed', component: true, only_for: ['cylindrical'] })
const GROUP: GroupSchema = {
  label: '구속',
  types: ['fixed_support', 'displacement', 'remote_displacement', 'frictionless', 'cylindrical', 'elastic_support'],
  fields: {
    name: {},
    type: { enum: ['fixed_support', 'displacement', 'remote_displacement', 'frictionless', 'cylindrical', 'elastic_support'] },
    on: {},
    cs: { type: 'string', default: 'global', only_for: ['displacement', 'remote_displacement'] },
    location: {
      title: '원격점',
      enum: ['centroid', 'cs_origin'],
      default: 'centroid',
      only_for: ['remote_displacement'],
      labels: { centroid: '선택 그룹의 중심', cs_origin: '좌표계의 원점' },
    },
    x: axis('X'),
    y: axis('Y'),
    z: axis('Z'),
    rx: axis('회전 X', ['remote_displacement']),
    ry: axis('회전 Y', ['remote_displacement']),
    rz: axis('회전 Z', ['remote_displacement']),
    stiffness: { title: '기초 강성', anyOf: [{ type: 'number' }, { type: 'null' }], description: '법선으로 단위 길이 눌리는 데 드는 압력', only_for: ['elastic_support'] },
    radial: cylinder('반지름', '원통 중심에서 바깥쪽'),
    axial: cylinder('축', '원통 축을 따라'),
    tangential: cylinder('접선', '원통 축 둘레로 도는 방향'),
  },
  required: [],
  implied: {
    fixed_support: [
      { label: 'X', hold: 'fixed', hint: '모든 이동을 막는다' },
      { label: 'Y', hold: 'fixed', hint: '' },
      { label: 'Z', hold: 'fixed', hint: '' },
    ],
    frictionless: [
      { label: '법선', hold: 'fixed', hint: '면에 수직' },
      { label: '접선', hold: 'free', hint: '면을 따라 미끄러진다' },
    ],
    elastic_support: [
      { label: '법선', hold: 'spring', hint: '기초 강성만큼 버틴다' },
      { label: '접선', hold: 'free', hint: '받치지 않는다' },
    ],
  },
}

const pressed = (axisName: string) =>
  screen.getByRole('group', { name: `${axisName} 구속` }).querySelector('[aria-pressed="true"]')?.textContent

test('성분은 **자유 · 고정 · 변위량**을 고른다 — 빈칸 · 0 을 알아서 읽게 두지 않는다', () => {
  let item: ConditionItem = { name: '받침', type: 'displacement', on: '바닥', x: null, y: 0, z: 0.5 }
  const view = () => <ConditionForm group={GROUP} item={item} names={[]} onChange={(next) => (item = next)} />
  const { rerender } = render(view())
  expect([pressed('X'), pressed('Y'), pressed('Z')]).toEqual(['자유', '고정', '변위량'])
  expect(screen.queryByLabelText('X 변위량')).toBeNull()
  expect(screen.getByLabelText('Z 변위량')).toHaveValue('0.5')

  // 변위량을 고르면 칸이 열리고, 아직 0 이어도 「고정」 으로 돌아가지 않는다.
  fireEvent.click(screen.getAllByRole('button', { name: '변위량' })[0])
  expect(item.x).toBe(0)
  rerender(view())
  expect(pressed('X')).toBe('변위량')
  fireEvent.change(screen.getByLabelText('X 변위량'), { target: { value: '=밀기' } })
  expect(item.x).toBe('=밀기')

  // 고정은 0, 자유는 null.
  rerender(view())
  fireEvent.click(screen.getAllByRole('button', { name: '자유' })[2])
  expect(item.z).toBeNull()
})

test('원통 지지는 **반지름 · 축 · 접선**마다 자유 · 고정을 고른다 — 좌표계 칸은 없다', () => {
  let item: ConditionItem = { name: '핀', type: 'cylindrical', on: '구멍' }
  const view = () => <ConditionForm group={GROUP} item={item} names={[]} onChange={(next) => (item = next)} />
  const { rerender } = render(view())
  expect([pressed('반지름'), pressed('축'), pressed('접선')]).toEqual(['고정', '고정', '고정'])
  expect(screen.queryByRole('group', { name: 'X 구속' })).toBeNull()
  expect(screen.queryByLabelText('좌표계')).toBeNull()
  expect(screen.getByText('원통 축 둘레로 도는 방향')).toBeInTheDocument()

  const turn = screen.getByRole('group', { name: '접선 구속' })
  fireEvent.click(turn.querySelector('button')!)
  expect(item.tangential).toBe('free')
  rerender(view())
  expect(pressed('접선')).toBe('자유')
})

test('종류가 정하는 방향은 **잠긴 단추**로 보인다 — 어느 방향이 어떻게 잡히는지', () => {
  const { rerender } = render(<ConditionForm group={GROUP} item={{ name: '고정', type: 'fixed_support', on: '바닥' }} names={[]} onChange={() => {}} />)
  expect([pressed('X'), pressed('Y'), pressed('Z')]).toEqual(['고정', '고정', '고정'])
  for (const button of screen.getByRole('group', { name: 'X 구속' }).querySelectorAll('button')) expect(button).toBeDisabled()
  expect(screen.queryByLabelText('X 변위량')).toBeNull()

  rerender(<ConditionForm group={GROUP} item={{ name: '미끄럼', type: 'frictionless', on: '바닥' }} names={[]} onChange={() => {}} />)
  expect([pressed('법선'), pressed('접선')]).toEqual(['고정', '자유'])
  expect(screen.getByText('면을 따라 미끄러진다')).toBeInTheDocument()
  expect(screen.getByText(/변경할 수 없습니다/)).toBeInTheDocument()
})

test('원격 변위는 이동 X · Y · Z 와 **회전 X · Y · Z** 를 고르고, 원격점을 사람 말로 고른다', () => {
  let item: ConditionItem = { name: '핀', type: 'remote_displacement', on: '구멍', x: 0, rz: null }
  const view = () => <ConditionForm group={GROUP} item={item} names={[]} onChange={(next) => (item = next)} />
  const { rerender } = render(view())
  expect([pressed('X'), pressed('회전 X'), pressed('회전 Z')]).toEqual(['고정', '자유', '자유'])
  expect(screen.getByLabelText('좌표계')).toBeInTheDocument()
  expect(screen.getByLabelText('원격점')).toHaveTextContent('선택 그룹의 중심')

  fireEvent.click(screen.getByRole('group', { name: '회전 Y 구속' }).querySelectorAll('button')[1])
  expect(item.ry).toBe(0)
  rerender(view())
  expect(pressed('회전 Y')).toBe('고정')
})

test('탄성 지지는 법선이 **스프링**으로 잠겨 보이고, 기초 강성을 적는다', () => {
  let item: ConditionItem = { name: '패드', type: 'elastic_support', on: '바닥' }
  render(<ConditionForm group={GROUP} item={item} names={[]} onChange={(next) => (item = next)} />)
  expect([pressed('법선'), pressed('접선')]).toEqual(['스프링', '자유'])
  expect(screen.queryByLabelText('좌표계')).toBeNull()
  fireEvent.change(screen.getByLabelText('기초 강성'), { target: { value: '0.2' } })
  expect(item.stiffness).toBe(0.2)
  expect(screen.getByText('법선으로 단위 길이 눌리는 데 드는 압력')).toBeInTheDocument()
})

const DIRECTED = ['pressure', 'force', 'standard_earth_gravity']
const LOADS: GroupSchema = {
  label: '하중',
  types: ['pressure', 'force', 'bolt_pretension', 'standard_earth_gravity'],
  fields: {
    name: {},
    type: { enum: ['pressure', 'force', 'bolt_pretension', 'standard_earth_gravity'], labels: { pressure: '압력', force: '힘' } },
    on: { only_for: ['pressure', 'force', 'bolt_pretension'] },
    cs: { type: 'string', default: 'global', only_for: DIRECTED },
    magnitude: { title: '크기', anyOf: [{ type: 'number' }, { type: 'null' }], only_for: ['pressure', 'force'], unit_by_type: true },
    unit: { type: 'string', default: '', hidden: true },
    direction: { title: '방향', direction: true, only_for: DIRECTED, normal_for: ['pressure'] },
    preload: { title: '예압', anyOf: [{ type: 'number' }, { type: 'null' }], only_for: ['bolt_pretension'], bolt: true },
  },
  required: [],
  notes: { force: '합계 힘 — 여러 면에 걸면 나눠 가집니다.' },
  dimensions: { pressure: 'stress', force: 'force' },
}
const MM = { force: 'N', stress: 'MPa', length: 'mm' }

test('하중의 크기에는 **단위계의 단위**가 붙고, 방향은 성분마다 적거나 빠른 단추로 고른다', () => {
  let item: ConditionItem = { name: '밀기', type: 'force', on: '윗면' }
  const view = () => <ConditionForm group={LOADS} item={item} names={[]} units={MM} onChange={(next) => (item = next)} />
  const { rerender } = render(view())
  expect(screen.getByLabelText('크기 (N)')).toBeInTheDocument()
  expect(screen.getByText('합계 힘 — 여러 면에 걸면 나눠 가집니다.')).toBeInTheDocument()
  expect(screen.queryByLabelText('unit')).toBeNull()
  // 힘은 법선을 고를 수 없다 — 성분 칸만.
  expect(screen.queryByRole('group', { name: '방향 방식' })).toBeNull()

  fireEvent.click(screen.getByRole('button', { name: '−Z' }))
  expect(item.direction).toEqual([0, 0, -1])
  rerender(view())
  fireEvent.change(screen.getByLabelText('방향 X'), { target: { value: '=기울기' } })
  expect(item.direction).toEqual(['=기울기', 0, -1])
})

test('압력은 **면의 법선**이 기본이고 성분으로 바꿀 수 있다', () => {
  let item: ConditionItem = { name: '누름', type: 'pressure', on: '윗면' }
  const view = () => <ConditionForm group={LOADS} item={item} names={[]} units={MM} onChange={(next) => (item = next)} />
  const { rerender } = render(view())
  expect(screen.getByLabelText('크기 (MPa)')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '면의 법선' })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.queryByLabelText('방향 X')).toBeNull()
  expect(screen.queryByLabelText('좌표계')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'X·Y·Z 성분' }))
  expect(item.direction).toEqual([0, 0, -1])
  rerender(view())
  expect(screen.getByLabelText('방향 Z')).toHaveValue('-1')
  expect(screen.getByLabelText('좌표계')).toBeInTheDocument()
})

test('볼트는 **예압(N) · 조임량(mm)** 을 고르고, 중력은 선택 그룹 없이 -Z 를 보인다', () => {
  let item: ConditionItem = { name: '조임', type: 'bolt_pretension', on: '볼트' }
  const view = () => <ConditionForm group={LOADS} item={item} names={[]} units={MM} onChange={(next) => (item = next)} />
  const { rerender } = render(view())
  expect(screen.getByRole('button', { name: '예압 (N)' })).toHaveAttribute('aria-pressed', 'true')
  fireEvent.click(screen.getByRole('button', { name: '조임량 (mm)' }))
  expect(item.unit).toBe('mm')
  rerender(view())
  fireEvent.change(screen.getByLabelText('조임량'), { target: { value: '0.1' } })
  expect(item).toMatchObject({ preload: 0.1, unit: 'mm' })

  rerender(<ConditionForm group={LOADS} item={{ name: '자중', type: 'standard_earth_gravity' }} names={[]} units={MM} onChange={() => {}} />)
  expect(screen.queryByText('선택 그룹')).toBeNull()
  expect(screen.getByLabelText('방향 Z')).toHaveValue('-1')
  expect(screen.queryByLabelText(/크기/)).toBeNull()
})

test('변위량에는 **단위계의 길이**가, 회전에는 도가 칸마다 붙는다 — SI 면 m', () => {
  const item: ConditionItem = { name: '핀', type: 'remote_displacement', on: '구멍', x: 0.001, rx: 2 }
  const { rerender } = render(<ConditionForm group={GROUP} item={item} names={[]} units={{ length: 'm' }} onChange={() => {}} />)
  expect(pressed('X')).toBe('변위량 (m)')
  expect(screen.getByLabelText('X 변위량')).toHaveAttribute('placeholder', '수 또는 =식 (m)')
  expect(pressed('회전 X')).toBe('변위량 (도)')
  rerender(<ConditionForm group={GROUP} item={item} names={[]} units={{ length: 'mm' }} onChange={() => {}} />)
  expect(pressed('X')).toBe('변위량 (mm)')
})

const CONTACTS: GroupSchema = {
  label: '접촉',
  types: ['bonded', 'frictional'],
  intro: '두 선택 그룹이 맞닿는 자리입니다.',
  fields: {
    name: {},
    type: { enum: ['bonded', 'frictional'], labels: { bonded: '본딩(붙음)', frictional: '마찰' } },
    source: { title: '접촉면 (contact)', description: '보통 작거나 볼록한 쪽' },
    target: { title: '대상면 (target)' },
    friction: { title: '마찰계수', anyOf: [{ type: 'number' }, { type: 'null' }], only_for: ['frictional'] },
    pinball: { title: 'pinball 반경', anyOf: [{ type: 'number' }, { type: 'null' }], unit: 'mm' },
    formulation: {
      title: '정식화',
      enum: ['program_controlled', 'mpc'],
      default: 'program_controlled',
      labels: { program_controlled: '프로그램이 정함', mpc: 'MPC(구속식)' },
    },
  },
  required: [],
  notes: { frictional: '눌리면 마찰계수만큼 버티다 미끄러집니다.' },
}

test('접촉은 **접촉면 · 대상면**과 종류마다 필요한 칸만, 고르는 칸은 사람 말로 보인다', () => {
  const view = (item: ConditionItem) => <ConditionForm group={CONTACTS} item={item} names={[]} onChange={() => {}} />
  const { rerender } = render(view({ name: '맞닿음', type: 'bonded', source: '윗판', target: '아랫판' }))
  expect(screen.getByText('두 선택 그룹이 맞닿는 자리입니다.')).toBeInTheDocument()
  expect(screen.getByText('접촉면 (contact)')).toBeInTheDocument()
  expect(screen.getByText('보통 작거나 볼록한 쪽')).toBeInTheDocument()
  expect(screen.getByLabelText('정식화')).toHaveTextContent('프로그램이 정함')
  expect(screen.getByLabelText('pinball 반경 (mm)')).toBeInTheDocument()
  expect(screen.queryByLabelText('마찰계수')).toBeNull()

  rerender(view({ name: '맞닿음', type: 'frictional', source: '윗판', target: '아랫판' }))
  expect(screen.getByLabelText('마찰계수')).toBeInTheDocument()
  expect(screen.getByText('눌리면 마찰계수만큼 버티다 미끄러집니다.')).toBeInTheDocument()
})

const INITIAL: GroupSchema = {
  label: '초기조건',
  types: ['environment_temperature', 'velocity'],
  fields: {
    type: { enum: ['environment_temperature', 'velocity'] },
    on: { title: '바디 선택 그룹', only_for: ['velocity'] },
    value: { title: '온도', anyOf: [{ type: 'number' }, { type: 'null' }], only_for: ['environment_temperature'], unit: '°C' },
    vector: { title: '속도', only_for: ['velocity'], unit: 'mm/s', components: true },
    unit: { type: 'string', default: '', hidden: true },
  },
  required: [],
}

test('초기 속도는 X · Y · Z 성분을 mm/s 로, 환경 온도는 °C 하나를 적는다', () => {
  let item: ConditionItem = { type: 'velocity', on: '몸' }
  const view = () => <ConditionForm group={INITIAL} item={item} names={[]} onChange={(next) => (item = next)} />
  const { rerender } = render(view())
  expect(screen.getByText('속도 (mm/s)')).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('속도 Z'), { target: { value: '-5000' } })
  expect(item.vector).toEqual([0, 0, -5000])
  expect(screen.queryByLabelText(/온도/)).toBeNull()

  item = { type: 'environment_temperature' }
  rerender(view())
  expect(screen.getByLabelText('온도 (°C)')).toBeInTheDocument()
  expect(screen.queryByText('바디 선택 그룹')).toBeNull()
})

test('국부 메시는 **「전체」** 를 고를 수 있다 — 요소 형상 · 차수는 「전체」 에만', () => {
  const MESH: GroupSchema = {
    label: '국부 메시',
    types: [],
    fields: {
      on: { title: '적용 대상', whole: '전체', default: '전체' },
      element_size: { title: '요소 크기', anyOf: [{ type: 'number' }, { type: 'null' }], unit: 'mm' },
      method: { title: '요소 형상', enum: ['automatic', 'tetrahedrons'], default: 'automatic', whole_only: true },
    },
    required: [],
    accepts: { '*': [{ entity: 'face' }, { entity: 'edge' }] },
  }
  const holes = [{ name: '구멍면', entity: 'face', select: {} }]
  const { rerender } = render(<ConditionForm group={MESH} item={{ on: '전체' }} names={holes} onChange={() => {}} />)
  expect(screen.getByLabelText('적용 대상')).toHaveTextContent('전체 (모든 바디)')
  expect(screen.getByLabelText('요소 크기 (mm)')).toBeInTheDocument()
  expect(screen.getByText('요소 형상')).toBeInTheDocument()
  expect(screen.queryByText(/선택 그룹이 없습니다/)).toBeNull()
  // 면 그룹을 촘촘하게 — 요소 형상은 면에 뜻이 없어 감춘다.
  rerender(<ConditionForm group={MESH} item={{ on: '구멍면' }} names={holes} onChange={() => {}} />)
  expect(screen.getByLabelText('요소 크기 (mm)')).toBeInTheDocument()
  expect(screen.queryByText('요소 형상')).toBeNull()
})

const ANALYSIS: GroupSchema = {
  label: '해석 설정',
  types: ['modal', 'thermal'],
  intro: '무엇을 풀지 고릅니다.',
  fields: {
    type: { enum: ['modal', 'thermal'], labels: { modal: '모달(고유진동)', thermal: '열' } },
    modes: { title: '모드 수', anyOf: [{ type: 'integer' }, { type: 'null' }], default: 6, only_for: ['modal'], integer: true },
    frequency_range: { title: '주파수 범위', only_for: ['modal'], unit: 'Hz', range: true },
    prestressed: { title: '선응력 반영', type: 'boolean', default: false, only_for: ['modal'] },
    thermal_mode: { title: '열 해석', enum: ['steady', 'transient'], default: 'steady', only_for: ['thermal'] },
    end_time: {
      title: '끝 시간',
      anyOf: [{ type: 'number' }, { type: 'null' }],
      only_for: ['thermal'],
      unit: 's',
      when: { thermal: { thermal_mode: 'transient' } },
    },
  },
  required: [],
  notes: { modal: '구조가 스스로 떠는 진동수를 찾습니다.' },
}

test('해석 설정은 종류마다 칸이 다르고, 켬 · 끔과 **최소 ~ 최대**를 제 모양으로 받는다', () => {
  let item: ConditionItem = { type: 'modal' }
  const view = () => <ConditionForm group={ANALYSIS} item={item} names={[]} onChange={(next) => (item = next)} />
  const { rerender } = render(view())
  expect(screen.getByText('구조가 스스로 떠는 진동수를 찾습니다.')).toBeInTheDocument()
  // 비우면 기본값 — 그것을 보여 준다.
  expect(screen.getByLabelText('모드 수')).toHaveAttribute('placeholder', '기본값 6')

  fireEvent.click(within(screen.getByRole('group', { name: '선응력 반영' })).getByRole('button', { name: '켬' }))
  expect(item.prestressed).toBe(true)
  rerender(view())
  fireEvent.change(screen.getByLabelText('주파수 범위 최대'), { target: { value: '500' } })
  expect(item.frequency_range).toEqual([0, 500])
  rerender(view())
  fireEvent.change(screen.getByLabelText('주파수 범위 최소'), { target: { value: '10' } })
  expect(item.frequency_range).toEqual([10, 500])
})

test('열 해석의 시간 칸은 **과도일 때만** 보인다', () => {
  const { rerender } = render(<ConditionForm group={ANALYSIS} item={{ type: 'thermal' }} names={[]} onChange={() => {}} />)
  expect(screen.queryByLabelText('끝 시간 (s)')).toBeNull()
  expect(screen.queryByLabelText('모드 수')).toBeNull()
  rerender(<ConditionForm group={ANALYSIS} item={{ type: 'thermal', thermal_mode: 'transient' }} names={[]} onChange={() => {}} />)
  expect(screen.getByLabelText('끝 시간 (s)')).toBeInTheDocument()
})

test('조건은 **받는 종류의 선택 그룹만** 고르게 하고, 받는 것을 적어 둔다', () => {
  const group: GroupSchema = {
    ...LOADS,
    accepts: { pressure: [{ entity: 'face' }], bolt_pretension: [{ entity: 'face', kind: 'cylinder' }, { entity: 'body' }] },
  }
  const edges = [{ name: '모서리', entity: 'edge', select: {} }] as never
  const { rerender } = render(<ConditionForm group={group} item={{ name: '누름', type: 'pressure', on: '' }} names={edges} units={MM} onChange={() => {}} />)
  expect(screen.getByText('적용 가능 대상: 면 선택 그룹')).toBeInTheDocument()
  // 엣지 그룹뿐이면 고를 것이 없다고 말한다.
  expect(screen.getByText(/사용할 수 있는 선택 그룹이 없습니다\. 3D에서 대상 형상\(면\)을/)).toBeInTheDocument()
  rerender(<ConditionForm group={group} item={{ name: '조임', type: 'bolt_pretension', on: '' }} names={edges} units={MM} onChange={() => {}} />)
  expect(screen.getByText('적용 가능 대상: 원통면, 바디 선택 그룹')).toBeInTheDocument()
})

test('종류가 없는 국부 메시는 `*` 규칙으로 받는 것을 보인다 — 바디는 파트별 설정으로', () => {
  const MESH: GroupSchema = {
    label: '국부 메시',
    types: [],
    fields: { on: { title: '적용 대상', whole: '전체' } },
    required: [],
    accepts: { '*': [{ entity: 'face' }, { entity: 'edge' }] },
  }
  render(<ConditionForm group={MESH} item={{ on: '전체' }} names={[]} onChange={() => {}} />)
  expect(screen.getByText('적용 가능 대상: 면, 엣지 선택 그룹')).toBeInTheDocument()
})

test('국부 메시의 대상을 면 그룹으로 바꾸면 「전체」 에만 쓰는 칸은 기본값으로 돌아간다', () => {
  const MESH: GroupSchema = {
    label: '국부 메시',
    types: [],
    fields: {
      on: { title: '적용 대상', whole: '전체', default: '전체' },
      method: { title: '요소 형상', enum: ['automatic', 'sweep'], default: 'automatic', whole_only: true },
    },
    required: [],
    accepts: { '*': [{ entity: 'face' }] },
  }
  const onChange = vi.fn()
  render(
    <ConditionForm group={MESH} item={{ on: '전체', method: 'sweep' }} names={[{ name: '구멍면', entity: 'face', select: {} }]} onChange={onChange} />,
  )
  fireEvent.click(screen.getByLabelText('적용 대상'))
  fireEvent.click(screen.getByRole('option', { name: '구멍면' }))
  expect(onChange).toHaveBeenLastCalledWith({ on: '구멍면', method: 'automatic' })
})

const HARMONIC_LOADS = ['force', 'acceleration']
const EXCITATION: GroupSchema = {
  label: '하중',
  types: ['force', 'acceleration', 'psd_acceleration'],
  fields: {
    name: {},
    type: { enum: ['force', 'acceleration', 'psd_acceleration'] },
    on: { only_for: ['force'] },
    cs: { type: 'string', default: 'global', only_for: ['force', 'acceleration', 'psd_acceleration'] },
    magnitude: { title: '크기', anyOf: [{ type: 'number' }, { type: 'null' }], only_for: ['force', 'acceleration'], unit_by_type: true },
    direction: { title: '방향', direction: true, only_for: ['force', 'acceleration', 'psd_acceleration'] },
    frequency_table: {
      title: '주파수별 배율',
      only_for: HARMONIC_LOADS,
      analysis_only: ['harmonic'],
      table: { columns: [{ title: '주파수', unit: 'Hz' }, { title: '배율' }] },
    },
    phase: { title: '위상', anyOf: [{ type: 'number' }, { type: 'null' }], only_for: HARMONIC_LOADS, analysis_only: ['harmonic'], unit: '°' },
    psd_table: {
      title: '가속도 PSD',
      only_for: ['psd_acceleration'],
      table: { columns: [{ title: '주파수', unit: 'Hz' }, { title: 'PSD', unit: 'g²/Hz' }], grms: true },
    },
  },
  required: [],
  dimensions: { force: 'force', acceleration: 'acceleration' },
}

test('주파수별 배율 · 위상은 **조화 응답일 때만** 보인다', () => {
  const item: ConditionItem = { name: '스윕', type: 'acceleration', magnitude: 9806.65, direction: [1, 0, 0] }
  const { rerender } = render(<ConditionForm group={EXCITATION} item={item} names={[]} analysis="static" onChange={() => {}} />)
  expect(screen.queryByText('주파수별 배율')).toBeNull()
  expect(screen.queryByLabelText('위상 (°)')).toBeNull()
  rerender(<ConditionForm group={EXCITATION} item={item} names={[]} analysis="harmonic" onChange={() => {}} />)
  expect(screen.getByText('주파수별 배율')).toBeInTheDocument()
  expect(screen.getByLabelText('위상 (°)')).toBeInTheDocument()
})

test('표는 엑셀에서 붙여 넣은 두 열로 채우고, 행을 고치고 지운다', () => {
  let item: ConditionItem = { name: '스윕', type: 'acceleration', magnitude: 9806.65, direction: [1, 0, 0] }
  const view = () => <ConditionForm group={EXCITATION} item={item} names={[]} analysis="harmonic" onChange={(next) => (item = next)} />
  const { rerender } = render(view())
  // 빈 표 — 붙여 넣을 칸이 있다.
  fireEvent.change(screen.getByLabelText('주파수별 배율 붙여넣기'), { target: { value: '주파수\t배율\n100\t0.5\n2000\t1' } })
  expect(item.frequency_table).toEqual([
    [100, 0.5],
    [2000, 1],
  ])
  rerender(view())
  fireEvent.change(screen.getByLabelText('주파수별 배율 2행 배율'), { target: { value: '=배율' } })
  expect(item.frequency_table).toEqual([
    [100, 0.5],
    [2000, '=배율'],
  ])
  rerender(view())
  fireEvent.click(screen.getByRole('button', { name: '행 추가' }))
  expect(item.frequency_table).toHaveLength(3)
  rerender(view())
  fireEvent.click(screen.getByRole('button', { name: '주파수별 배율 3행 삭제' }))
  fireEvent.click(screen.getByRole('button', { name: '주파수별 배율 1행 삭제' }))
  rerender(view())
  fireEvent.click(screen.getByRole('button', { name: '모두 지우기' }))
  expect(item.frequency_table).toBeNull()
})

test('곡선을 가리키는 하중은 표 대신 그 곡선을 쓴다고 말하고, 떼면 표로 적는다', () => {
  const group: GroupSchema = { ...EXCITATION, fields: { ...EXCITATION.fields, curve: { type: 'string', default: '', hidden: true, only_for: ['psd_acceleration'] } } }
  let item: ConditionItem = { name: 'X 랜덤', type: 'psd_acceleration', direction: [1, 0, 0], curve: 'IEC 랜덤' }
  const view = () => <ConditionForm group={group} item={item} names={[]} analysis="random" onChange={(next) => (item = next)} />
  const { rerender } = render(view())
  expect(screen.getByRole('status')).toHaveTextContent('가속도 PSD: 곡선 ‘IEC 랜덤’의 점을 씁니다')
  expect(screen.queryByLabelText('가속도 PSD 붙여넣기')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '곡선 떼고 표로 입력' }))
  expect(item.curve).toBe('')
  rerender(view())
  expect(screen.getByLabelText('가속도 PSD 붙여넣기')).toBeInTheDocument()
})

/** 곡선을 가리킬 수 있는 하중 — 가속도 PSD(로그-로그 · g^2/Hz)와 조화의 주파수별 배율(선형 · 단위 없음). */
const CURVE_USES = {
  psd_acceleration: { field: 'psd_table', interpolation: 'loglog', unit: 'g^2/Hz' },
  acceleration: { field: 'frequency_table', interpolation: 'linear', unit: '' },
}
const WITH_CURVE: GroupSchema = {
  ...EXCITATION,
  fields: { ...EXCITATION.fields, curve: { type: 'string', default: '', hidden: true, only_for: ['acceleration', 'psd_acceleration'] } },
}
const SWEEP: CurveItem = { name: '스윕', x: 'frequency', unit: '', interpolation: 'linear', points: [[10, 1], [100, 0.5]], scale: 2 }
const RANDOM: CurveItem = { name: 'IEC 랜덤', x: 'frequency', unit: 'g^2/Hz', interpolation: 'loglog', points: [[20, 0.04], [2000, 0.04]] }

test('표 아래에서 곡선을 고른다 — 맞지 않는 곡선은 까닭과 함께 막고, 고르면 표 대신 곡선을 가리킨다', () => {
  let item: ConditionItem = { name: '흔듦', type: 'acceleration', magnitude: 9806.65, direction: [1, 0, 0], frequency_table: [[10, 1]] }
  const view = () => (
    <ConditionForm group={WITH_CURVE} item={item} names={[]} analysis="harmonic" curves={[SWEEP, RANDOM]} curveUses={CURVE_USES} onMakeCurve={() => {}} onChange={(next) => (item = next)} />
  )
  const { rerender } = render(view())
  const pick = screen.getByLabelText('주파수별 배율 곡선')
  expect(screen.getByRole('option', { name: '스윕' })).not.toBeDisabled()
  expect(screen.getByRole('option', { name: /^IEC 랜덤 — 선형 보간이어야 합니다/ })).toBeDisabled()
  // 한 점뿐인 표는 곡선이 될 수 없다(두 점 이상).
  expect(screen.getByRole('button', { name: '표를 곡선으로 저장' })).toBeDisabled()
  fireEvent.change(pick, { target: { value: '스윕' } })
  expect(item).toMatchObject({ curve: '스윕', frequency_table: null })
  rerender(view())
  // 고른 곡선 — 무엇을 쓰는지와 그 그래프(배율을 곱한 값).
  expect(screen.getByRole('status')).toHaveTextContent('주파수별 배율: 곡선 ‘스윕’의 점을 씁니다. 곡선은 트리의 ‘곡선’에서 고칩니다')
  expect(screen.getByRole('img', { name: /곡선 ‘스윕’ 그래프 — 2점, .*값 1 ~ 2/ })).toBeInTheDocument()
  // 떼면 점 × 배율이 표로 옮겨진다.
  fireEvent.click(screen.getByRole('button', { name: '곡선 떼고 표로 입력' }))
  expect(item).toMatchObject({
    curve: '',
    frequency_table: [
      [10, 2],
      [100, 1],
    ],
  })
})

test('표를 곡선으로 저장하면 한 벌의 곡선에 더하고 이 하중이 그것을 가리킨다', () => {
  let item: ConditionItem = { name: 'X 랜덤', type: 'psd_acceleration', direction: [1, 0, 0], psd_table: [[20, 0.04], [2000, '=p']] }
  const made: CurveItem[] = []
  render(
    <ConditionForm
      group={WITH_CURVE}
      item={item}
      names={[]}
      analysis="random"
      curves={[RANDOM]}
      curveUses={CURVE_USES}
      onMakeCurve={(curve) => made.push(curve)}
      onChange={(next) => (item = next)}
    />,
  )
  // 맞는 곡선은 고를 수 있다.
  expect(screen.getByRole('option', { name: 'IEC 랜덤' })).not.toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: '표를 곡선으로 저장' }))
  expect(made).toEqual([
    { name: 'X 랜덤 곡선', x: 'frequency', interpolation: 'loglog', unit: 'g^2/Hz', points: [[20, 0.04], [2000, '=p']], scale: 1 },
  ])
  expect(item).toMatchObject({ curve: 'X 랜덤 곡선', psd_table: null })
})

test('없는 곡선을 가리키면 그렇다고 말한다', () => {
  render(
    <ConditionForm
      group={WITH_CURVE}
      item={{ name: 'X 랜덤', type: 'psd_acceleration', direction: [1, 0, 0], curve: '지운 곡선' }}
      names={[]}
      analysis="random"
      curves={[RANDOM]}
      curveUses={CURVE_USES}
      onChange={() => {}}
    />,
  )
  expect(screen.getByRole('status')).toHaveTextContent('이 이름의 곡선이 없습니다.')
})

test('가속도 PSD 는 선택 그룹 · 크기 없이 방향과 PSD 표를 받고, 표의 Grms 를 보인다', () => {
  let item: ConditionItem = { name: 'X 랜덤', type: 'psd_acceleration', direction: [1, 0, 0] }
  const view = () => <ConditionForm group={EXCITATION} item={item} names={[]} analysis="random" onChange={(next) => (item = next)} />
  const { rerender } = render(view())
  expect(screen.queryByLabelText('크기')).toBeNull()
  expect(screen.queryByText('선택 그룹')).toBeNull()
  fireEvent.change(screen.getByLabelText('가속도 PSD 붙여넣기'), { target: { value: '20\t0.04\n2000\t0.04' } })
  rerender(view())
  // √(0.04 × 1980) = 8.90
  expect(screen.getByText('Grms 8.90 g')).toBeInTheDocument()
  expect(screen.getByRole('columnheader', { name: 'PSD (g²/Hz)' })).toBeInTheDocument()
})
