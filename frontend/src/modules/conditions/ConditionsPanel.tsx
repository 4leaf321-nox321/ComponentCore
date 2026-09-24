/**
 * 「해석 조건」 — 작업 화면의 둘째 탭. **이것이 시뮬레이션 모드다.**
 *
 * 도면(CAD 모드)은 형상을 만들고, 여기서는 이미 있는 형상 **위에** 조건을 붙인다. 형상을 안
 * 바꾸므로 새 버전이 생기지 않는다.
 *
 * ## 도면 편집기와 같은 모양
 *
 * 위에 **리본**(더하는 단추 — 선택 그룹 · 물성 · 구속 · 하중 …), 왼쪽에 **모델 구성
 * 트리**(있는 것 — 파트 · 물성 · 선택 그룹 · 조건), 나머지는 3D 다. 부품 · 지그를 그리는 화면과 같은 자리에 같은
 * 일이 있어야 두 모드를 오갈 때 손이 헤매지 않는다.
 *
 * 조건은 **3D 를 가리지 않는 창**에서 고친다 — 창을 띄운 채 3D 에서 적용 대상을 선택하면
 * 그 조건의 대상으로 지정된다(`ConditionWindows`).
 *
 * ## 선택 그룹을 먼저, 조건은 그 위에
 *
 * 조건은 면을 직접 가리키지 않고 **선택 그룹만** 가리킨다(데이터의 `named_selections` —
 * 화면의 말은 「선택 그룹」 이다). 선택 그룹은 좌표가 아니라 셀렉터로 저장되므로(「아래쪽 면」 ·
 * 「반지름 4.25 원통면」) 실험계획이 치수를 바꿔도 설계점마다 다시 풀린다. 3D 에서 선택하면
 * 서버가 후보를 주고(`/cad/recipe/selectors`) **사람이 고른다** — 하나를 자동으로 정하면
 * 「볼트 구멍 넷」 을 원했는데 「이 구멍 하나」 가 저장되는 날이 온다.
 *
 * **여럿을 한 그룹으로 묶는다** — Ctrl(⌘)은 넣고 빼기, Shift 는 더하기, **Shift + 끌기는 사각형
 * 선택**(온전히 든 것 · 가려진 것은 빼고). 고른 것마다 제 규칙을 두고 그 합을 그룹으로 한다
 * (`{"any": [...]}`, 서버의 `query.select_features`).
 */

import {
  Anchor,
  ArrowDownToLine,
  FlaskConical,
  Grid3x3,
  Group,
  Link2,
  Save,
  Scale,
  Settings2,
  Thermometer,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'

import type { Recipe } from '@/modules/cad/api'
import { RibbonButton, RibbonGroup } from '@/modules/cad/Ribbon'
import { useRecipeMesh } from '@/modules/cad/useRecipeMesh'
import { ConditionForm } from '@/modules/conditions/ConditionForm'
import { FloatingWindow, SelectionMembers } from '@/modules/conditions/ConditionWindows'
import type { Member } from '@/modules/conditions/ConditionWindows'
import { materialColor, ModelTree, UNASSIGNED_COLOR } from '@/modules/conditions/ModelTree'
import type { TreeSelection } from '@/modules/conditions/ModelTree'
import { materialsApi } from '@/modules/materials/api'
import type { MaterialRow } from '@/modules/materials/api'
import { MaterialPicker } from '@/modules/materials/MaterialPicker'
import {
  asConditions,
  assignBody,
  conditionsApi,
  defaultRule,
  GROUP_KEYS,
  materialsOn,
} from '@/modules/conditions/api'
import type {
  ConditionItem,
  Conditions,
  ConditionsSchema,
  GroupSchema,
  MaterialItem,
  NamedSelection,
  SelectorCandidate,
} from '@/modules/conditions/api'
import { ApiError } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { useFillHeight } from '@/shared/hooks/useFillHeight'
import { Button } from '@/shared/components/ui/button'
import { Card, CardContent } from '@/shared/components/ui/card'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { useResource } from '@/shared/hooks/useResource'
import type { MeasureMarks, MeasurePick, PickModifiers } from '@/shared/viewer/PickViewer'
import PickViewer from '@/shared/viewer/PickViewer'

/**
 * 창에서 고치는 조건 하나 — **확인을 눌러야 한 벌에 들어간다.** `index` 가 `null` 이면 새로
 * 더하는 것이다. 취소하면 아무것도 안 바뀐다(3D 에서 만든 선택 그룹은 남는다 — 그것은
 * 그것대로 쓸모가 있다).
 */
type Editing = { group: string; index: number | null; item: ConditionItem } | null

/** 3D 에서 찍은 것 → 서버에 물을 말. */
function toPick(pick: MeasurePick): { what: string; point: number[]; label: string } {
  if (pick.kind === 'point') return { what: 'vertices', point: pick.at, label: '점' }
  if (pick.kind === 'edge') return { what: 'edges', point: pick.edge.midpoint, label: '엣지' }
  if (pick.kind === 'body') return { what: 'bodies', point: [], label: '바디' }
  return { what: 'faces', point: pick.face.center, label: '면' }
}

/**
 * **무엇을 선택 대상인가.** 켠 것 하나만 잡힌다.
 *
 * 이것이 없으면 엣지를 고르려는데 점이 먼저 잡힌다 — 뷰어가 점 · 엣지 · 면 순으로 걸기
 * 때문이고, 그 순서를 사람이 바꿀 길이 없었다.
 *
 * 바디는 면을 눌러 고른다(덩어리를 겨눌 화면 요소가 따로 없다) — 그래서 면과 바디는
 * 동시에 켜면 안 된다. 하나씩만 켜는 것이 곧 그 문제도 푼다.
 */
const PICK_KINDS = [
  // 작은 것에서 큰 것으로 — 점 · 엣지 · 면 · 바디.
  { key: 'point', label: '점', entity: 'vertex', what: 'vertices' },
  { key: 'edge', label: '엣지', entity: 'edge', what: 'edges' },
  { key: 'face', label: '면', entity: 'face', what: 'faces' },
  { key: 'body', label: '바디', entity: 'body', what: 'bodies' },
] as const

type PickKind = (typeof PICK_KINDS)[number]['key']

/** 리본 단추의 그림 — 조건 묶음마다 하나. */
const GROUP_ICONS: Record<string, LucideIcon> = {
  constraints: Anchor,
  loads: ArrowDownToLine,
  contacts: Link2,
  initial: Thermometer,
  mesh_hints: Grid3x3,
}

/** 이 묶음의 조건이 선택 그룹을 가리키는 칸 — 접촉은 둘(원본 · 상대)이다. */
function targetFields(group: GroupSchema | undefined): string[] {
  if (!group) return []
  if ('source' in group.fields) return ['source', 'target']
  return 'on' in group.fields ? ['on'] : []
}

export function ConditionsPanel({
  recipe,
  value,
  onSave,
  saving,
}: {
  recipe: Recipe
  value: unknown
  onSave: (next: Conditions) => void
  saving?: boolean
}) {
  const [draft, setDraft] = useState<Conditions>(() => asConditions(value))
  /** 트리에서 펼친 것 — 파트 · 물성 · 선택 그룹. */
  const [tree, setTree] = useState<TreeSelection>(null)
  const [editing, setEditing] = useState<Editing>(null)
  /** 3D 에서 고른 것들 — 「선택 그룹 추가」 창이나 조건 창이 이것으로 그룹을 만든다. */
  const [members, setMembers] = useState<Member[]>([])
  /** 「선택 그룹 추가」 창이 떠 있나. */
  const [grouping, setGrouping] = useState(false)
  const [groupName, setGroupName] = useState('')
  const [picking, setPicking] = useState(false)
  /** 지금 선택할 종류 — 하나만. 기본은 면(조건이 가장 많이 붙는 자리다). */
  const [pickKind, setPickKind] = useState<PickKind>('face')
  /** 초기조건 창이 바디로 바꿔 놓기 전의 선택 대상 — 창을 닫으면 되돌린다. */
  const pickKindBefore = useRef<PickKind | null>(null)
  const [error, setError] = useState<Error | null>(null)

  const schema = useResource<ConditionsSchema>(() => conditionsApi.schema(), [])
  const { mesh, problems } = useRecipeMesh(recipe)

  useEffect(() => setDraft(asConditions(value)), [value])

  const names = draft.named_selections
  /** 저장한 것과 다른가 — 리본의 「조건 저장」 이 눈에 띄게 한다. */
  const dirty = useMemo(() => JSON.stringify(draft) !== JSON.stringify(asConditions(value)), [draft, value])

  /**
   * 그 조건이 가리킬 수 있는 선택 그룹만.
   *
   * **초기조건은 바디에 건다** — 온도 · 속도 · 예응력은 몸 전체의 상태이지 한 면의 것이
   * 아니다. 면 그룹을 고를 수 있게 두면 해석 쪽에서야 「그 자리에 못 건다」 를 안다.
   */
  function namesFor(group: string): NamedSelection[] {
    if (group === 'initial') return names.filter((one) => one.entity === 'body')
    return names
  }

  /** 창에서 고치는 조건이 3D 선택을 받는가 — 선택 그룹을 가리키는 칸이 있어야 한다. */
  const editingTargets = editing ? targetFields(schema.data?.groups[editing.group]) : []

  /** 같은 것을 다시 눌렀는지 가르는 열쇠 — 면 · 엣지는 번호, 점은 좌표, 바디는 이름. */
  function memberKey(pick: MeasurePick): string {
    if (pick.kind === 'point') return `point:${pick.at.map((v) => v.toFixed(3)).join(',')}`
    if (pick.kind === 'edge') return `edge:${pick.edge.index}`
    if (pick.kind === 'face') return `face:${pick.face.index}`
    return `body:${pick.name}`
  }

  /**
   * 3D 에서 누른 것을 **담는다.** 아무것도 안 누르면 새로 고르고, Ctrl(⌘)은 넣고 빼기, Shift 는
   * 더하기다 — CAD 에서 손에 익은 그대로.
   *
   * 조건 창이 떠 있으면 그 창이 받고, 아니면 「선택 그룹 추가」 창이 받는다(없으면 연다).
   */
  async function ask(pick: MeasurePick, mods: PickModifiers = { ctrl: false, shift: false }) {
    setError(null)
    if (!editing || editingTargets.length === 0) setGrouping(true)
    const key = memberKey(pick)
    const had = members.some((one) => one.key === key)
    if (mods.ctrl && had) {
      setMembers((now) => now.filter((one) => one.key !== key))
      return
    }
    if (mods.shift && had) return
    const { what, point, label } = toPick(pick)
    let candidates: SelectorCandidate[]
    // **바디는 서버에 물을 것이 없다.** 면 · 엣지 · 점은 「이 자리를 무엇으로 부를까」 를
    // 셀렉터 후보로 되받아야 하지만, 바디는 **이름이 곧 답**이다(`topology.bodies`).
    if (pick.kind === 'body') {
      candidates = [{ label: `바디 「${pick.name}」`, select: { body: pick.name }, matches: 1 }]
    } else {
      try {
        candidates = (await conditionsApi.selectors(recipe, what, point)).candidates
      } catch (failure) {
        setError(failure instanceof ApiError ? failure : new Error(String(failure)))
        return
      }
    }
    if (candidates.length === 0) return
    // 기본 규칙은 **고른 그것 하나**를 가리키고 치수에 흔들리지 않는 것 — 하나씩 골라 묶는
    // 중이므로. 좌표만 쓰는 규칙은 DOE 에서 딴 형상을 집으므로 기본으로 두지 않는다. 같은
    // 반지름의 구멍 넷처럼 부류 전부가 필요하면 목록에서 바꾼다(몇 개에 맞는지 함께 보인다).
    const chosen = defaultRule(candidates)
    const entity = PICK_KINDS.find((one) => one.what === what)?.entity ?? 'face'
    const member: Member = { key, label, entity, pick, candidates, chosen }
    setMembers((now) => {
      if (!mods.ctrl && !mods.shift) return [member]
      return now.some((one) => one.key === key) ? now : [...now, member]
    })
  }

  /**
   * 사각형으로 고른 것들을 **더한다**(Shift). 이미 담긴 것은 건너뛰고, 규칙 후보는 서버에
   * **한 번에** 묻는다 — 하나씩 물으면 고른 수만큼 도면을 다시 만든다.
   */
  async function addMany(picks: MeasurePick[]) {
    if (picks.length === 0) return
    setError(null)
    if (!editing || editingTargets.length === 0) setGrouping(true)
    const seen = new Set(members.map((one) => one.key))
    const fresh = picks.filter((pick) => {
      const key = memberKey(pick)
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
    const asking = fresh.filter((pick) => pick.kind !== 'body').map(toPick)
    let answers: { candidates: SelectorCandidate[] }[] = []
    if (asking.length > 0) {
      try {
        answers = (await conditionsApi.selectorsMany(recipe, asking.map(({ what, point }) => ({ what, point })))).items
      } catch (failure) {
        setError(failure instanceof ApiError ? failure : new Error(String(failure)))
        return
      }
    }
    let at = 0
    const made: Member[] = []
    for (const pick of fresh) {
      const { what, label } = toPick(pick)
      const candidates =
        pick.kind === 'body'
          ? [{ label: `바디 「${pick.name}」`, select: { body: pick.name }, matches: 1 }]
          : (answers[at++]?.candidates ?? [])
      if (candidates.length === 0) continue
      const chosen = defaultRule(candidates)
      const entity = PICK_KINDS.find((one) => one.what === what)?.entity ?? 'face'
      made.push({ key: memberKey(pick), label, entity, pick, candidates, chosen })
    }
    setMembers((now) => [...now, ...made.filter((one) => !now.some((have) => have.key === one.key))])
  }

  /** 담은 것들의 규칙 — 하나면 그 규칙, 여럿이면 **합**(`{"any": [...]}`). */
  function groupSelect(list: Member[]): Record<string, unknown> {
    const rules = list.map((one) => one.candidates[one.chosen].select)
    return rules.length === 1 ? rules[0] : { any: rules }
  }

  /** 같은 규칙의 선택 그룹이 이미 있으면 그 이름 — 새로 만들지 않고 그것을 쓴다. */
  const existing = useMemo(() => {
    if (members.length === 0) return null
    const select = JSON.stringify(groupSelect(members))
    const same = names.find((one) => one.entity === members[0].entity && JSON.stringify(one.select) === select)
    return same?.name ?? null
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [members, names])

  /** 이름을 안 적으면 — 첫 규칙의 말에 「외 N」. */
  const defaultName =
    members.length === 0
      ? ''
      : `${members[0].candidates[members[0].chosen].label}${members.length > 1 ? ` 외 ${members.length - 1}` : ''}`

  /**
   * 담은 것으로 선택 그룹을 만든다 — 같은 규칙의 그룹이 있으면 새로 만들지 않고 그것을 쓴다.
   * 쓸 이름과 새 한 벌을 돌려준다(못 만들면 `null`).
   */
  function makeGroup(): { name: string; draft: Conditions } | null {
    if (members.length === 0) return null
    if (existing) return { name: existing, draft }
    const name = groupName.trim() || defaultName
    if (names.some((one) => one.name === name)) {
      setError(new Error(`「${name}」 선택 그룹이 이미 있습니다 — 다른 이름을 입력하세요.`))
      return null
    }
    const made: NamedSelection = { name, entity: members[0].entity, select: groupSelect(members) }
    return { name, draft: { ...draft, named_selections: [...names, made] } }
  }

  function clearMembers() {
    setMembers([])
    setGroupName('')
  }

  function closeGroup() {
    setGrouping(false)
    clearMembers()
  }

  /** 「선택 그룹 추가」 창의 생성 — 만든 그룹을 트리에서 펼쳐 보인다. */
  function createGroup() {
    const made = makeGroup()
    if (!made) return
    setDraft(made.draft)
    setGrouping(false)
    clearMembers()
    setError(null)
    setTree({ kind: 'selection', index: made.draft.named_selections.findIndex((one) => one.name === made.name) })
  }

  /**
   * 조건 창을 띄운 채 3D 를 선택했을 때 — 그룹을 만들고 **그 조건의 대상으로 지정한다.**
   * 그룹을 따로 만들고 다시 조건으로 돌아가 목록에서 고르면 한 가지 일이 세 걸음이 된다.
   * 접촉은 원본이 비었으면 원본, 아니면 상대에 넣는다.
   */
  function assignGroup() {
    if (!editing) return
    const made = makeGroup()
    if (!made) return
    const key = editingTargets.find((one) => !editing.item[one]) ?? editingTargets[editingTargets.length - 1]
    setDraft(made.draft)
    setEditing({ ...editing, item: { ...editing.item, [key]: made.name } })
    clearMembers()
    setError(null)
  }

  /**
   * 담은 것을 3D 에 **번호와 함께** — 목록의 몇 번이 어디인지 보인다. 바디는 그 파트의 면 전부
   * (단품은 면에 파트 이름이 없고 바디가 「전체」 하나다).
   */
  const marks = useMemo<MeasureMarks | undefined>(() => {
    if (members.length === 0) return undefined
    const out: MeasureMarks = { points: [], segments: [], labels: [], edges: [], faces: [] }
    members.forEach((member, index) => {
      const text = String(index + 1)
      const pick = member.pick
      if (pick.kind === 'point') {
        out.points.push(pick.at)
        out.labels.push({ at: pick.at, text, tone: 'entity' })
      } else if (pick.kind === 'edge') {
        out.edges.push({ points: pick.edge.points, tone: 'live' })
        out.labels.push({ at: pick.edge.midpoint, text, tone: 'entity' })
      } else if (pick.kind === 'face') {
        out.faces.push({ vertices: pick.face.vertices, triangles: pick.face.triangles, tone: 'live' })
        out.labels.push({ at: pick.face.center, text, tone: 'entity' })
      } else {
        for (const face of mesh?.faces ?? []) {
          if ((face.part || '전체') === pick.name) {
            out.faces.push({ vertices: face.vertices, triangles: face.triangles, tone: 'live' })
          }
        }
      }
    })
    return out
  }, [members, mesh])

  /**
   * 창을 연다 — 초기조건이면 선택 대상을 바디로 바꾼다(바디에만 건다).
   *
   * 트리에서 펼친 파트는 접는다 — 펼친 파트만 또렷하고 나머지는 반투명이라, 그대로 두면
   * 적용 대상을 선택할 3D 가 흐리게 남는다.
   */
  function openWindow(next: NonNullable<Editing>) {
    setError(null)
    setTree(null)
    // 적용 대상을 받는 창이면 「선택 그룹 추가」 창은 닫되 **담은 것은 넘긴다** — 먼저 고르고
    // 조건을 더하는 순서(해석 전처리기에서 흔한 순서)도 된다. 초기조건은 바디만 받는다.
    if (targetFields(schema.data?.groups[next.group]).length > 0) {
      setGrouping(false)
      if (next.group === 'initial' && members.some((one) => one.entity !== 'body')) clearMembers()
    }
    if (next.group === 'initial' && pickKind !== 'body') {
      pickKindBefore.current = pickKind
      setPickKind('body')
    }
    setEditing(next)
  }

  function closeWindow() {
    if (editingTargets.length > 0) clearMembers()
    setEditing(null)
    if (pickKindBefore.current) {
      setPickKind(pickKindBefore.current)
      pickKindBefore.current = null
    }
  }

  /** 리본에서 조건을 더한다 — 창이 뜨고, 확인을 눌러야 한 벌에 들어간다. */
  function addItem(group: string) {
    const spec = schema.data?.groups[group]
    if (!spec) return
    const item: ConditionItem = { type: spec.types[0] }
    if ('name' in spec.fields) item.name = `${spec.label} ${(draft[group as keyof Conditions] as ConditionItem[]).length + 1}`
    if ('on' in spec.fields) item.on = namesFor(group)[0]?.name ?? ''
    openWindow({ group, index: null, item })
  }

  function openItem(group: string, index: number) {
    const item = (draft[group as keyof Conditions] as ConditionItem[])[index]
    if (item) openWindow({ group, index, item: structuredClone(item) })
  }

  function confirmWindow() {
    if (!editing) return
    if (editing.group === 'analysis') {
      setDraft({ ...draft, analysis: editing.item })
    } else {
      const list = [...(draft[editing.group as keyof Conditions] as ConditionItem[])]
      if (editing.index === null) list.push(editing.item)
      else list[editing.index] = editing.item
      setDraft({ ...draft, [editing.group]: list })
    }
    closeWindow()
  }

  function removeEditing() {
    if (!editing || editing.index === null || editing.group === 'analysis') return
    const list = (draft[editing.group as keyof Conditions] as ConditionItem[]).filter((_, i) => i !== editing.index)
    setDraft({ ...draft, [editing.group]: list })
    closeWindow()
  }

  function removeSelection(index: number) {
    const gone = names[index]
    setDraft({
      ...draft,
      named_selections: names.filter((_, i) => i !== index),
      // 가리키던 조건은 남겨 두되 빈 칸이 된다 — 저장할 때 서버가 짚어 준다.
      ...Object.fromEntries(
        GROUP_KEYS.map((key) => [
          key,
          (draft[key] ?? []).map((one) => {
            const next = { ...one }
            for (const field of ['on', 'source', 'target']) if (next[field] === gone?.name) next[field] = ''
            return next
          }),
        ]),
      ),
    })
    setTree(null)
  }

  /**
   * 트리와 3D 가 함께 쓸 높이 — 화면 아래까지. 위쪽 줄이 바뀌면 다시 잰다.
   *
   * **조기 반환보다 위**에 있어야 한다. 아래에 두면 로딩 중 렌더와 그 뒤 렌더의 훅 수가
   * 달라져 React 가 상태를 잘못 잇는다(시험이 그걸 잡았다).
   */
  const fill = useFillHeight<HTMLDivElement>({
    /**
     * **바닥값은 격자 전체의 높이다** — 그 안 뷰어가 520 이 되게: 3D 칸의 「선택 대상」 줄
     * (~34px)과 여유를 더했다. 뷰어 높이로 바닥값을 주면 뷰어가 그만큼 작아진다(실측 2026-09-24).
     */
    min: 520 + 82,
    /** 격자 아래에는 아무것도 없다 — 「조건 저장」 은 리본으로 올라갔다. */
    gap: 12,
  })

  /**
   * 물성이 붙을 수 있는 자리 — 조립이면 구성품마다, 단품이면 「전체」 하나.
   *
   * **서버가 정하는 이름을 그대로 받는다.** 메시의 면에서 지어내면 내보낼 때 쓰는 이름과
   * 어긋나는 날이 오고, 그때 사람이 고른 바디가 폴더에 없는 이름이 된다.
   */
  const bodies = useResource(() => conditionsApi.bodies(recipe), [recipe])

  /**
   * 물성마다 **낼 수 있는 솔버 덱 형식.** 고른 것은 중립 물성 옆에 덤으로 나간다 —
   * 받는 쪽이 제 덱을 손으로 짜는 대신 그대로 쓴다.
   *
   * **기본은 안 담는다.** 덱은 솔버별이라 담는 순간 솔버를 고르는 것이고, 우리 계약은
   * 솔버를 모르는 것이다. 고르는 것은 사람이다.
   */
  const [deckChoices, setDeckChoices] = useState<Record<string, { key: string; ready: boolean }[]>>({})
  useEffect(() => {
    let alive = true
    for (const one of draft.materials) {
      const ref = (one.ref ?? {}) as Record<string, unknown>
      const id = String(ref.material_id ?? '')
      if (!id || deckChoices[id]) continue
      const source = String(ref.source ?? '').includes('literature') ? 'literature' : 'registered'
      void materialsApi
        .deckFormats(id, source)
        .then((got) => alive && setDeckChoices((now) => ({ ...now, [id]: got.items })))
        .catch(() => alive && setDeckChoices((now) => ({ ...now, [id]: [] })))
    }
    return () => {
      alive = false
    }
  }, [draft.materials, deckChoices])

  const bodyNames = useMemo(() => (bodies.data?.items ?? []).map((one) => one.name), [bodies.data])

  /**
   * 3D 의 파트 색 = 그 파트에 지정한 물성의 색(트리의 네모와 같다). 아직 없는 파트는 회색.
   *
   * **물성을 하나도 안 담았으면 칠하지 않는다** — 전부 회색이 되어 조건을 붙이는 화면이 흐려
   * 보인다. 단품은 면에 파트 이름이 없어 칠할 수 없고, 칠할 까닭도 없다(파트가 하나다).
   *
   * 뷰어는 이 값이 바뀌면 장면을 다시 짓는다 — 그래서 물성 지정이 바뀔 때만 새로 만든다.
   */
  const partColors = useMemo(() => {
    if (draft.materials.length === 0 || bodyNames.length < 2) return undefined
    return Object.fromEntries(
      bodyNames.map((name) => {
        const on = materialsOn(draft.materials, name)
        return [name, on.length ? materialColor(on[0]) : UNASSIGNED_COLOR]
      }),
    )
  }, [draft.materials, bodyNames])

  /** 파트에 물성을 지정한다 — 파트 하나에 물성 하나(다른 물성에서는 빠진다). */
  function assign(body: string, index: number | null) {
    setDraft({ ...draft, materials: assignBody(draft.materials, bodyNames, body, index) })
  }

  /**
   * 탐색기에서 담은 물성들을 더한다. 이미 담긴 재료(그쪽 id 가 같은 것)는 다시 담지 않는다.
   *
   * **아직 어디에도 안 붙인다**(`apply_to: []`) — 어느 파트에 무엇을 줄지는 트리에서 파트를
   * 누르며 정한다. 단품만 예외다: 파트가 하나뿐이라 고를 것이 없으니, 비어 있으면 첫 물성을
   * 붙인다.
   */
  function addMaterials(rows: MaterialRow[]) {
    const have = new Set(draft.materials.map((one) => String((one.ref ?? {}).material_id ?? '')))
    const fresh: MaterialItem[] = rows
      .filter((row) => !have.has(row.id))
      .map((row) => ({
        apply_to: [],
        ref: {
          source:
            row.source === 'catalog'
              ? 'matnexus-catalog'
              : row.source === 'literature'
                ? 'matnexus-literature'
                : 'matnexus',
          // **그쪽 id** — 덱을 뽑으려면 이것이 필요하다(번호로는 카드를 못 찾고, 문헌은
          // 번호가 없는 것이 많다).
          material_id: row.id,
          code: row.code,
          name: row.name,
          fetched_at: new Date().toISOString(),
        },
        // **payload 통째로** 싣는다 — 「어느 것이 영률인가」 는 솔버를 아는 쪽의 일이다.
        payload: row.payload,
      }))
    let materials: MaterialItem[] = [...draft.materials, ...fresh]
    if (bodyNames.length === 1 && fresh.length > 0 && materialsOn(materials, bodyNames[0]).length === 0) {
      materials = assignBody(materials, bodyNames, bodyNames[0], draft.materials.length)
    }
    setDraft({ ...draft, materials })
    setPicking(false)
    // **곧바로 「어느 파트에」 로 간다** — 비어 있는 첫 파트를 펼쳐 둔다. 나중으로 미루면
    // 담아만 두고 잊는다.
    const empty = bodyNames.find((name) => materialsOn(materials, name).length === 0)
    setTree(empty ? { kind: 'part', name: empty } : null)
  }

  if (schema.loading) return <Skeleton className="h-96 w-full" />
  if (schema.error) return <ErrorNotice error={schema.error} />
  const spec = schema.data!
  const system = draft.units?.system ?? 'mm_n_tonne'
  const systemOf = spec.unit_systems?.find((one) => one.key === system)
  /** 창을 띄웠으면 바디만 되는 조건인가 — 선택 대상 단추를 그에 맞게 막는다. */
  const bodyOnly = editing?.group === 'initial'
  const editingSpec: GroupSchema | undefined =
    editing?.group === 'analysis'
      ? {
          label: '해석 설정',
          types: (spec.analysis.properties?.type?.enum ?? []) as string[],
          fields: spec.analysis.properties ?? {},
          required: [],
        }
      : editing
        ? spec.groups[editing.group]
        : undefined

  return (
    <div className="space-y-3">
      {/*
        **리본** — 도면 편집기와 같은 단추. 더하는 일은 여기서 하고, 있는 것은 왼쪽 트리에서
        보고 고친다. 「조건 저장」 도 여기 있다 — 격자 아래에 두면 3D 가 그만큼 작아진다.
      */}
      <div className="flex flex-wrap gap-2 rounded-md border p-2">
        <RibbonGroup title="저장">
          <RibbonButton
            icon={Save}
            label="조건 저장"
            title={editing ? '열린 창을 먼저 확인하거나 취소합니다' : '도면은 변경되지 않습니다 — 새 버전이 생기지 않습니다'}
            active={dirty}
            disabled={saving || !!editing}
            onClick={() => onSave(draft)}
          />
        </RibbonGroup>
        <RibbonGroup title="선택">
          <RibbonButton
            icon={Group}
            label="선택 그룹"
            title={
              editing && editingTargets.length > 0
                ? '열린 조건 창에서 3D 를 선택하면 그 조건의 선택 그룹이 됩니다'
                : '선택 그룹 추가 — 3D 에서 Ctrl · Shift 로 여럿을 선택합니다'
            }
            active={grouping}
            disabled={!!editing && editingTargets.length > 0}
            onClick={() => {
              if (grouping) return closeGroup()
              clearMembers()
              setGrouping(true)
            }}
          />
        </RibbonGroup>
        <RibbonGroup title="물성">
          <RibbonButton
            icon={FlaskConical}
            label="물성"
            title="물성 추가 — MatNexus 에서 여러 개를 함께 선택합니다"
            onClick={() => setPicking(true)}
          />
        </RibbonGroup>
        <RibbonGroup title="조건">
          {GROUP_KEYS.map((group) => (
            <RibbonButton
              key={group}
              icon={GROUP_ICONS[group] ?? Settings2}
              label={spec.groups[group]?.label ?? group}
              title={`${spec.groups[group]?.label ?? group} 추가`}
              onClick={() => addItem(group)}
            />
          ))}
        </RibbonGroup>
        <RibbonGroup title="해석">
          <RibbonButton
            icon={Settings2}
            label="해석 설정"
            onClick={() => openWindow({ group: 'analysis', index: null, item: structuredClone(draft.analysis) as ConditionItem })}
          />
          {/*
            **단위계는 한 벌에 하나다.** 조건에 적힌 숫자와 물성 값이 같은 계로 풀려야 해석이
            맞는다 — MatNexus 는 밀도만 mm·t·s 로 주고 나머지는 SI 로 주므로, 이것이 없으면
            밀도는 맞고 탄성계수가 10⁶ 배 틀린 채로 나간다.
          */}
          <label
            className="bg-card flex h-14 shrink-0 flex-col items-center justify-center gap-1 rounded-md border px-2 text-[11px] leading-none shadow-sm"
            title={`단위계 — ${systemOf?.label ?? system}. 물성은 이 단위계로 환산하여 원본과 함께 전달됩니다(원본은 변경하지 않습니다).`}
          >
            <Scale className="size-5" />
            <select
              aria-label="단위계"
              className="bg-transparent text-[11px]"
              value={system}
              onChange={(e) => setDraft({ ...draft, units: { system: e.target.value } })}
            >
              {(spec.unit_systems ?? []).map((one) => (
                <option key={one.key} value={one.key}>
                  {one.length} · {one.stress}
                </option>
              ))}
            </select>
          </label>
        </RibbonGroup>
      </div>

      {error && <ErrorNotice error={error} />}
      {problems.length > 0 && (
        <p className="text-muted-foreground text-xs">
          도면에 문제가 있어 3D 가 표시되지 않습니다 — 「도면」 탭에서 수정합니다.
        </p>
      )}

      {/*
        **트리와 3D 가 남은 높이를 함께 쓴다.** 3D 를 굳혀 두면 큰 화면에서 아래가 비고, 면을
        고르려고 돌려 볼 자리가 모자란다. 트리는 길어질 수 있으므로 **칸 안에서 스크롤**한다 —
        페이지가 통째로 늘어나면 3D 가 화면 밖으로 밀린다.
      */}
      <div ref={fill.ref} style={fill.style} className="grid min-h-0 gap-3 lg:grid-cols-[300px_1fr]">
        {/*
          `py-0` — `h-full` 은 Card 높이의 100% 라, Card 에 세로 여백이 있으면 그만큼
          **넘쳐서 잘린다**(`overflow-hidden`). 여백은 안쪽(`p-3`)이 갖는다.
        */}
        <Card className="min-h-0 overflow-hidden py-0">
          <CardContent className="h-full overflow-y-auto p-3 text-sm">
            <ModelTree
              bodies={bodies.data?.items ?? null}
              bodiesError={bodies.error}
              materials={draft.materials}
              decks={deckChoices}
              names={names}
              groups={GROUP_KEYS.map((key) => ({
                key,
                label: spec.groups[key]?.label ?? key,
                items: draft[key] ?? [],
              }))}
              analysis={[String(draft.analysis?.type ?? ''), systemOf ? `${systemOf.length} · ${systemOf.stress}` : '']
                .filter(Boolean)
                .join(' · ')}
              editing={editing}
              selected={tree}
              onSelect={setTree}
              onAssign={assign}
              onMaterialChange={(index, patch) =>
                setDraft({
                  ...draft,
                  materials: draft.materials.map((one, i) => (i === index ? { ...one, ...patch } : one)),
                })
              }
              onRemoveMaterial={(index) => {
                setDraft({ ...draft, materials: draft.materials.filter((_, i) => i !== index) })
                setTree(null)
              }}
              onPickMaterials={() => setPicking(true)}
              onRemoveSelection={removeSelection}
              onOpenItem={openItem}
              onOpenAnalysis={() =>
                openWindow({ group: 'analysis', index: null, item: structuredClone(draft.analysis) as ConditionItem })
              }
            />
          </CardContent>
        </Card>

        {/* ── 3D ── */}
        {/* `py-0` — 3D 는 칸을 통째로 쓴다. Card 의 세로 여백이 그만큼 뷰어를 깎았다. */}
        <Card className="flex min-h-0 flex-col gap-0 overflow-hidden py-0">
          {/*
            **무엇을 선택할지 먼저 고른다.** 없을 때는 엣지를 고르려는데 점이 먼저 잡혔다 —
            뷰어가 점 · 엣지 · 면 순으로 걸고, 그 순서를 사람이 바꿀 길이 없었다.
          */}
          <div className="flex shrink-0 flex-wrap items-center gap-1 border-b px-2 py-1.5">
            <span className="text-muted-foreground mr-1 text-xs">선택 대상</span>
            {PICK_KINDS.map((one) => (
              <button
                key={one.key}
                type="button"
                aria-pressed={pickKind === one.key}
                disabled={bodyOnly && one.key !== 'body'}
                title={bodyOnly && one.key !== 'body' ? '초기조건은 바디에만 적용됩니다' : undefined}
                className={`rounded border px-2 py-0.5 text-xs disabled:opacity-40 ${
                  pickKind === one.key
                    ? 'border-primary bg-accent font-medium'
                    : 'text-muted-foreground hover:bg-accent/50'
                }`}
                onClick={() => {
                  if (one.key === pickKind) return
                  setPickKind(one.key)
                  // **한 그룹은 한 종류다** — 종류를 바꾸면 담아 둔 것은 비운다.
                  clearMembers()
                }}
              >
                {one.label}
              </button>
            ))}
            <span className="text-muted-foreground ml-auto text-xs">
              {pickKind === 'body' && '면을 클릭하면 그 바디가 선택됩니다 · '}
              {editing && editingTargets.length > 0
                ? '선택하면 열린 조건의 적용 대상이 됩니다 — Ctrl · Shift 로 여럿, Shift + 끌기는 사각형'
                : grouping
                  ? 'Ctrl · Shift 로 더하고, Shift + 끌기로 사각형 안의 것을 더합니다'
                  : '3D 에서 선택하면 선택 그룹을 만듭니다'}
            </span>
          </div>
          <CardContent className="min-h-0 flex-1 p-0">
            <PickViewer
              mesh={mesh}
              mode="measure"
              // **켠 것 하나만.** 바디는 면을 눌러 고르므로 면과 함께 켜면 안 된다.
              measureKinds={{
                point: pickKind === 'point',
                edge: pickKind === 'edge',
                face: pickKind === 'face',
                body: pickKind === 'body',
              }}
              onMeasure={(pick, mods) => void ask(pick, mods)}
              // Shift + 끌기 — 사각형 안에 온전히 든 것(가려진 것은 빼고)을 더한다.
              onBoxSelect={(picks) => void addMany(picks)}
              // 담은 것을 번호와 함께 표시한다 — 목록의 몇 번이 어디인지.
              measureMarks={marks}
              partColors={partColors}
              // 트리에서 파트를 누르면 3D 에서도 그 파트만 또렷하게 — 어느 것에 지정하는지 보인다.
              emphasis={tree?.kind === 'part' && bodyNames.length > 1 ? tree.name : null}
              className="h-full w-full"
            />
          </CardContent>
        </Card>
      </div>

      {/* ── 조건 창 — 3D 를 가리지 않는다. 띄운 채 3D 에서 적용 대상을 지정한다. ── */}
      <FloatingWindow
        open={!!editing && !!editingSpec}
        title={
          editing?.group === 'analysis'
            ? '해석 설정'
            : `${editingSpec?.label ?? ''} ${editing?.index === null ? '추가' : '수정'}`
        }
        description={
          editingTargets.length === 0
            ? undefined
            : bodyOnly
              ? '초기조건은 바디에만 적용됩니다 — 3D 에서 바디를 선택하면 적용 대상으로 지정됩니다.'
              : '3D 에서 형상을 선택하면 적용 대상으로 지정됩니다 — Ctrl · Shift 로 여럿을 묶습니다.'
        }
        onClose={closeWindow}
        footer={
          <>
            {editing && editing.index !== null && editing.group !== 'analysis' && (
              <Button variant="ghost" className="sm:mr-auto" onClick={removeEditing}>
                삭제
              </Button>
            )}
            <Button variant="ghost" onClick={closeWindow}>
              취소
            </Button>
            <Button onClick={confirmWindow}>확인</Button>
          </>
        }
      >
        {editing && editingSpec && (
          <>
            {members.length > 0 && editingTargets.length > 0 && (
              <SelectionMembers
                members={members}
                onChoose={(index, candidate) =>
                  setMembers((now) => now.map((one, i) => (i === index ? { ...one, chosen: candidate } : one)))
                }
                onRemove={(index) => setMembers((now) => now.filter((_, i) => i !== index))}
                onClear={clearMembers}
                name={groupName}
                onName={setGroupName}
                placeholder={defaultName}
                existing={existing}
                actions={
                  <Button size="sm" onClick={assignGroup}>
                    적용 대상으로 지정
                  </Button>
                }
              />
            )}
            <ConditionForm
              group={editingSpec}
              item={editing.item}
              names={editing.group === 'analysis' ? names : namesFor(editing.group)}
              onChange={(next) => setEditing({ ...editing, item: next })}
            />
          </>
        )}
      </FloatingWindow>

      {/*
        ── 선택 그룹 추가 — 리본 단추로 열거나, 창 없이 3D 를 선택하면 열린다. Ctrl(⌘)은 넣고
        빼기, Shift 는 더하기. 여럿이면 규칙들의 합으로 저장된다.
      */}
      <FloatingWindow
        open={grouping}
        title="선택 그룹 추가"
        description="3D 에서 형상을 선택합니다 — Ctrl 또는 Shift 를 누른 채 선택하면 여럿을 담고, Shift 를 누른 채 끌면 사각형 안에 온전히 든 것을 담습니다. 한 그룹은 한 종류(점 · 엣지 · 면 · 바디)입니다."
        onClose={closeGroup}
        // 해석 설정 창과 함께 뜨는 드문 경우 겹치지 않게 조금 아래에 세운다.
        className={editing ? 'top-56' : 'top-24'}
        footer={
          <>
            <Button variant="ghost" onClick={closeGroup}>
              취소
            </Button>
            <Button onClick={createGroup} disabled={members.length === 0 || !!existing}>
              생성
            </Button>
          </>
        }
      >
        <SelectionMembers
          members={members}
          onChoose={(index, candidate) =>
            setMembers((now) => now.map((one, i) => (i === index ? { ...one, chosen: candidate } : one)))
          }
          onRemove={(index) => setMembers((now) => now.filter((_, i) => i !== index))}
          onClear={clearMembers}
          name={groupName}
          onName={setGroupName}
          placeholder={defaultName}
          existing={existing}
        />
      </FloatingWindow>

      <MaterialPicker
        open={picking}
        onClose={() => setPicking(false)}
        // 조건 한 벌이 고른 계로 보여 준다 — 검산한 값이 그대로 나가야 한다.
        system={system}
        added={draft.materials.map((one) => String((one.ref ?? {}).material_id ?? '')).filter(Boolean)}
        onAdd={addMaterials}
      />
    </div>
  )
}

export type { NamedSelection }
