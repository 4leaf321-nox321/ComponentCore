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
 *
 * ## 나눈 것(구조 정리 ①)
 *
 * 이 파일은 상태를 들고 잇는다. 그리는 것 · 셈하는 것은 옆 파일에 있다 — 케이스 탭(`CaseTabs` · `cases`), 리본
 * (`ConditionsRibbon`), 준비 점검(`ReadinessPanel` · `readiness`), 모델 트리(`ModelTree`), 3D 에 비출 것
 * (`useConditionMarks`), 3D 에서 담기(`useGroupPicking`), 좌표계(`useConditionFrames`), 3D 칸 위의 것
 * (`ViewportOverlays`), 조건 창(`ConditionWindows` · `ConditionForm`), 곡선(`CurveForm` · `curves` · `CurvePlot`).
 */

import { Scale } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'

import type { Recipe } from '@/modules/cad/api'
import { FrameForm } from '@/modules/cad/FrameForm'
import type { FrameDraft, Placing } from '@/modules/cad/FrameForm'
import { frameFields, framePlacement, methodOf, numericFrame } from '@/modules/cad/frameMath'
import { nextFrameName } from '@/modules/cad/FramesDialog'
import { keptLabel, MeasureDialog } from '@/modules/cad/MeasureDialog'
import type { KeptMeasure, PickKind as MeasureKind } from '@/modules/cad/MeasureDialog'
import type { Pick as MeasuredPick } from '@/modules/cad/measure'
import { measureMarks } from '@/modules/cad/measureMarks'
import { useRecipeMesh } from '@/modules/cad/useRecipeMesh'
import { CaseTabs } from '@/modules/conditions/CaseTabs'
import { caseView, casesOf, putCaseView, saved, withCases } from '@/modules/conditions/cases'
import { ConditionForm } from '@/modules/conditions/ConditionForm'
import { ConditionsRibbon } from '@/modules/conditions/ConditionsRibbon'
import { ContactCheck } from '@/modules/conditions/ContactCheck'
import { CurveForm } from '@/modules/conditions/CurveForm'
import type { CurvePreset } from '@/modules/conditions/CurveForm'
import { curveUsers, emptyCurve, renameCurve } from '@/modules/conditions/curves'
import { FloatingWindow, SelectionMembers } from '@/modules/conditions/ConditionWindows'
import { materialColor, ModelTree, UNASSIGNED_COLOR } from '@/modules/conditions/ModelTree'
import type { TreeSelection } from '@/modules/conditions/ModelTree'
import { materialsApi } from '@/modules/materials/api'
import type { MaterialRow } from '@/modules/materials/api'
import { MaterialPicker } from '@/modules/materials/MaterialPicker'
import { PartSettingsDialog } from '@/modules/conditions/PartSettingsDialog'
import { readiness } from '@/modules/conditions/readiness'
import type { ReadinessOpen } from '@/modules/conditions/readiness'
import { ReadinessPanel } from '@/modules/conditions/ReadinessPanel'
import { useConditionFrames } from '@/modules/conditions/useConditionFrames'
import { useConditionMarks } from '@/modules/conditions/useConditionMarks'
import { PICK_KINDS, useGroupPicking } from '@/modules/conditions/useGroupPicking'
import { ContactLegend, PickKindBar, SectionControls } from '@/modules/conditions/ViewportOverlays'
import type { PickKind } from '@/modules/conditions/useGroupPicking'
import {
  acceptsLabel,
  asConditions,
  assignBody,
  conditionsApi,
  GROUP_KEYS,
  materialsOn,
  moveBodyMeshHints,
} from '@/modules/conditions/api'
import type {
  ConditionItem,
  Conditions,
  ConditionsSchema,
  CurveItem,
  GroupSchema,
  MaterialItem,
  NamedSelection,
  ExpressionNote,
  TargetKind,
} from '@/modules/conditions/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { useFillHeight } from '@/shared/hooks/useFillHeight'
import { Button } from '@/shared/components/ui/button'
import { Card, CardContent } from '@/shared/components/ui/card'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { useResource } from '@/shared/hooks/useResource'
import type { Section } from '@/shared/viewer/PickViewer'
import PickViewer from '@/shared/viewer/PickViewer'
import { DEFAULT_MATERIAL_TEMPERATURE } from '@/modules/materials/MaterialProperties'

/**
 * 창에서 고치는 조건 하나 — **확인을 눌러야 한 벌에 들어간다.** `index` 가 `null` 이면 새로
 * 더하는 것이다. 취소하면 아무것도 안 바뀐다(3D 에서 만든 선택 그룹은 남는다 — 그것은
 * 그것대로 쓸모가 있다).
 */
type Editing = { group: string; index: number | null; item: ConditionItem } | null

/** 이 묶음의 조건이 선택 그룹을 가리키는 칸 — 접촉은 둘(원본 · 상대)이다. */
function targetFields(group: GroupSchema | undefined): string[] {
  if (!group) return []
  if ('source' in group.fields) return ['source', 'target']
  return 'on' in group.fields ? ['on'] : []
}

interface PanelProps {
  recipe: Recipe
  value: unknown
  onSave: (next: Conditions) => void
  saving?: boolean
  /** 작업의 기본 단위계 — 아직 조건이 없으면 이 계로 시작한다. */
  defaultSystem?: string
}

/**
 * 해석 조건 화면. **해석 케이스가 있는 조건(v2)은 케이스 탭으로 연다**(`CaseTabs`) — 트리 · 3D · 창은 고른
 * 케이스 하나를 v1 모양(공유 칸 + 그 케이스 칸, `caseView`)으로 그리고 고친다. 고친 것은 공유 칸은 맨 위로, 케이스
 * 칸은 그 케이스로 돌아가고(`putCaseView`), 저장할 때 맨 위의 케이스 칸은 뺀다(`saved` — 섞이면 서버가 막는다).
 * 케이스가 없는 조건(v1)은 지금과 같다.
 */
export function ConditionsPanel({ recipe, value, onSave, saving, defaultSystem }: PanelProps) {
  /**
   * 저장된 조건 — **바디 그룹에 건 옛 국부 메시는 파트별 설정으로 옮겨 읽는다**(`moveBodyMeshHints`).
   * 옮긴 것은 초안에만 있고 「조건 저장」 을 눌러야 남는다(그래서 저장 단추가 켜진다).
   */
  const loaded = useMemo(() => moveBodyMeshHints(asConditions(value, defaultSystem)), [value, defaultSystem])
  /** 고치는 중인 한 벌 전부 — 케이스가 있으면 케이스 모두. 화면은 그중 고른 케이스(`draft`)를 그린다. */
  const [whole, setWhole] = useState<Conditions>(() => loaded.conditions)
  const [active, setActive] = useState(0)
  const cases = casesOf(whole)
  /** 고른 케이스의 v1 모양 — 아래의 모든 것이 이것을 읽는다. 케이스가 없으면 한 벌 그대로. */
  const draft = useMemo(() => caseView(whole, active), [whole, active])
  /** 고친 v1 모양을 한 벌로 — 공유 칸은 맨 위로, 케이스 칸은 고른 케이스로. */
  const setDraft = (next: Conditions) => setWhole((now) => putCaseView(now, active, next))
  /** 트리에서 펼친 것 — 파트 · 물성 · 선택 그룹. */
  const [tree, setTree] = useState<TreeSelection>(null)
  const [editing, setEditing] = useState<Editing>(null)
  /** 「선택 그룹 추가」 창이 떠 있나. */
  const [grouping, setGrouping] = useState(false)
  const [picking, setPicking] = useState(false)
  /** 파트별 설정 표 — 물성 · 거동 · 표현 · 해석 제외 · 메시를 파트마다 한 줄로. */
  const [partsOpen, setPartsOpen] = useState(false)
  /** 좌표계 창 — 새로(`index` 가 null) 또는 고치는 것. 확인을 눌러야 한 벌에 들어간다. */
  const [frameEditing, setFrameEditing] = useState<{ index: number | null; item: FrameDraft } | null>(null)
  /** 곡선 창 — 새로(`index` 가 null) 또는 고치는 것. 확인을 눌러야 한 벌에 들어간다. */
  const [curveEditing, setCurveEditing] = useState<{ index: number | null; item: CurveItem } | null>(null)
  /** 좌표계를 화면에서 지정하는 중인 것 — 점 · 선 · 면을 누르거나 손잡이로 돌리기. */
  const [placing, setPlacing] = useState<Placing>(null)
  /**
   * **측정** — 도면 편집기와 같은 창이다. 켜 있는 동안 3D 선택은 선택 그룹이 아니라 재는 데
   * 쓴다(조건을 걸 자리의 거리 · 지름을 확인하려고).
   */
  const [measuring, setMeasuring] = useState(false)
  const [measures, setMeasures] = useState<MeasuredPick[]>([])
  const [kept, setKept] = useState<KeptMeasure[]>([])
  const [measureKinds, setMeasureKinds] = useState<Set<MeasureKind>>(new Set<MeasureKind>(['point', 'edge', 'face']))
  /** 지금 선택할 종류 — 하나만. 기본은 면(조건이 가장 많이 붙는 자리다). */
  const [pickKind, setPickKind] = useState<PickKind>('face')
  /** 초기조건 창이 바디로 바꿔 놓기 전의 선택 대상 — 창을 닫으면 되돌린다. */
  const pickKindBefore = useRef<PickKind | null>(null)
  const [error, setError] = useState<Error | null>(null)
  /**
   * 식 알림 — 값 칸의 식 중 풀리지 않는 것(저장 · 내보내기에서 막히기 전에). 고칠 때마다
   * 부르면 요청이 쏟아지므로 잠깐 멈췄을 때 한 번.
   */
  const [notes, setNotes] = useState<ExpressionNote[]>([])
  const notesKey = JSON.stringify([...GROUP_KEYS.map((key) => draft[key]), draft.body_settings, recipe.params])
  useEffect(() => {
    let alive = true
    const timer = setTimeout(() => {
      conditionsApi
        .notes(draft, recipe)
        .then((got) => alive && setNotes(got.items ?? []))
        .catch(() => alive && setNotes([]))
    }, 400)
    return () => {
      alive = false
      clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notesKey])

  const schema = useResource<ConditionsSchema>(() => conditionsApi.schema(), [])
  const { mesh, problems } = useRecipeMesh(recipe)

  // 저장된 것이 바뀔 때만 다시 읽는다 — 작업의 기본 단위계를 바꿨다고 고치던 것을 지우지 않는다.
  useEffect(() => {
    setWhole(loaded.conditions)
    setActive((now) => Math.min(now, Math.max(casesOf(loaded.conditions).length - 1, 0)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  const names = draft.named_selections
  /** 저장한 것과 다른가 — 리본의 「조건 저장」 이 눈에 띄게 한다. */
  const dirty = useMemo(
    () => JSON.stringify(saved(whole)) !== JSON.stringify(saved(asConditions(value, defaultSystem))),
    [whole, value, defaultSystem],
  )

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
  /**
   * 열린 조건의 **대상 칸** — 그 종류가 쓰는 것만(`only_for`). 중력 · 가속도 · 가속도 PSD 는 대상이
   * 없다 — 그런데도 창이 「3D에서 선택하면 적용 대상」 이라 말하고, 누르면 숨은 칸에 그룹을 넣었다.
   */
  const editingTargets = editing
    ? targetFields(schema.data?.groups[editing.group]).filter((key) => {
        const only = schema.data?.groups[editing.group]?.fields[key]?.only_for
        return !only || only.includes(String(editing.item.type ?? ''))
      })
    : []

  /**
   * 3D 에서 고른 것들(`useGroupPicking`) — 「선택 그룹 추가」 창이나 조건 창이 이것으로 그룹을 만든다. 누르기
   * 시작하면 조건 창이 받지 않는 한 「선택 그룹 추가」 창을 연다.
   */
  const { members, setMembers, groupName, setGroupName, clearMembers, ask, addMany, groupSelect, existing, defaultName } = useGroupPicking({
    recipe,
    names,
    onStart: () => {
      setError(null)
      if (!editing || editingTargets.length === 0) setGrouping(true)
    },
    onError: setError,
  })

  /**
   * 담은 것으로 선택 그룹을 만든다 — 같은 규칙의 그룹이 있으면 새로 만들지 않고 그것을 쓴다.
   * 쓸 이름과 새 한 벌을 돌려준다(못 만들면 `null`).
   */
  function makeGroup(): { name: string; draft: Conditions } | null {
    if (members.length === 0) return null
    if (existing) return { name: existing, draft }
    const name = groupName.trim() || defaultName
    if (names.some((one) => one.name === name)) {
      setError(new Error(`‘${name}’ 선택 그룹이 이미 존재합니다. 다른 이름을 입력하십시오.`))
      return null
    }
    const made: NamedSelection = { name, entity: members[0].entity, select: groupSelect(members) }
    return { name, draft: { ...draft, named_selections: [...names, made] } }
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


  /** 좌표계 — 도면의 것 · 조건의 것 · 고치는 중인 것, 그리고 3D 에 그릴 축(`useConditionFrames`). */
  const { cadFrames, conditionFrames, frameNames, frameRows } = useConditionFrames({ recipe, names, frames: draft.coordinate_systems, editing: frameEditing })

  /** 좌표계 창에서 화면으로 지정하는 중인가 — 그 좌표계의 숫자 시작값(식이면 서버가 푼 축에서). */
  const placingFrame = frameEditing && !frameEditing.item.on ? frameEditing.item : undefined
  const frameStart = placingFrame
    ? numericFrame(placingFrame, frameRows.find((one) => one.name === placingFrame.name))
    : null
  const placePick = !!frameStart && (placing === 'point' || placing === 'edge' || placing === 'face')
  function setFrameItem(origin: number[], rotate: number[]) {
    if (frameEditing) setFrameEditing({ ...frameEditing, item: { ...frameEditing.item, ...frameFields(methodOf(frameEditing.item), origin, rotate) } })
  }

  /**
   * **접촉 보기** — 접촉마다 양쪽 면 그룹을 지금 형상에서 풀어 본딩(tie)은 붉게, 그 밖의 접촉은
   * 푸르게 칠한다. 조립에서 어느 면이 붙고 어느 면이 미끄러지는지가 보여야 빠뜨린 접촉 · 잘못 고른
   * 종류가 드러난다. 켰을 때만 푼다(그룹마다 서버에 묻는다).
   */
  const [showContacts, setShowContacts] = useState(false)
  /**
   * **단면 · 투시** — 큰 부품에 가려 작은 부품의 접촉면이 안 보일 때. 단면은 축에 수직인 평면으로
   * 잘라(잘린 쪽은 눌러도 안 잡힌다) 안쪽을 보이고, 투시는 모두 옅게 해 표시를 위에 그린다.
   */
  const [section, setSection] = useState<Section | null>(null)
  const [xray, setXray] = useState(false)
  /** 3D 에서 숨긴 파트 — 트리의 눈 단추. 큰 파트를 숨겨 그 안의 작은 파트 · 접촉면을 본다. */
  const [hiddenParts, setHiddenParts] = useState<string[]>([])
  const sectionRange = (axis: Section['axis']) => {
    const at = { x: 0, y: 1, z: 2 }[axis]
    return mesh ? { min: mesh.bbox.min[at], max: mesh.bbox.max[at] } : { min: 0, max: 1 }
  }
  function toggleSection() {
    if (section) return setSection(null)
    const { min, max } = sectionRange('x')
    setSection({ axis: 'x', at: Math.round(((min + max) / 2) * 1000) / 1000 })
  }

  /** 3D 에 비출 것 — 담은 것 · 트리에서 고른 그룹 · 고치는 조건의 자리 · 접촉 표시(`useConditionMarks`). */
  const { marks, litCount, contactCounts, editRefs, contactEditing } = useConditionMarks({
    recipe,
    mesh,
    names,
    contacts: draft.contacts,
    members,
    tree,
    editing,
    editingTargets,
    showContacts,
  })

  /**
   * 창을 연다 — 초기조건이면 선택 대상을 바디로 바꾼다(바디에만 건다).
   *
   * 트리에서 펼친 파트는 접는다 — 펼친 파트만 또렷하고 나머지는 반투명이라, 그대로 두면
   * 적용 대상을 선택할 3D 가 흐리게 남는다.
   */
  /** 그 조건이 받는 선택 그룹 종류 — 없으면(대상이 없거나 모든 것) null. */
  function acceptsOf(group: string, type: unknown): TargetKind[] | null {
    const accepts = schema.data?.groups[group]?.accepts
    // 종류가 없는 묶음(메시 힌트)은 `*` 가 모든 경우다.
    return accepts?.[String(type ?? '')] ?? accepts?.['*'] ?? null
  }

  /**
   * 3D 에서 누를 것을 **그 조건이 받는 것으로** 맞춘다 — 압력 창이면 면, 초기 속도면 바디.
   * 받지 않는 것을 담아 두었으면 비운다. 창을 닫으면 원래 고르던 것으로 돌아간다.
   */
  function fitPicking(accepts: TargetKind[] | null) {
    if (!accepts) return
    const allowed = new Set<string>(accepts.map((one) => one.entity))
    if (members.some((one) => !allowed.has(one.entity))) clearMembers()
    const current = PICK_KINDS.find((one) => one.key === pickKind)
    if (current && !allowed.has(current.entity)) {
      if (pickKindBefore.current === null) pickKindBefore.current = pickKind
      setPickKind(PICK_KINDS.find((one) => allowed.has(one.entity))?.key ?? pickKind)
    }
  }

  function openWindow(next: NonNullable<Editing>) {
    setError(null)
    setTree(null)
    // 적용 대상을 받는 창이면 「선택 그룹 추가」 창은 닫되 **담은 것은 넘긴다** — 먼저 고르고
    // 조건을 더하는 순서(해석 전처리기에서 흔한 순서)도 된다.
    if (targetFields(schema.data?.groups[next.group]).length > 0) setGrouping(false)
    fitPicking(acceptsOf(next.group, next.item.type))
    setEditing(next)
  }

  // 창 안에서 종류를 바꾸면(힘 → 압력) 3D 에서 누를 것도 따라 맞춘다.
  const editingKind = editing && editing.group !== 'analysis' ? `${editing.group}:${String(editing.item.type ?? '')}` : ''
  useEffect(() => {
    if (editing && editing.group !== 'analysis') fitPicking(acceptsOf(editing.group, editing.item.type))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editingKind])

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
    // 「전체」 를 고를 수 있는 칸(메시 힌트)은 전체로 시작한다.
    if ('on' in spec.fields) item.on = spec.fields.on?.whole ?? namesFor(group)[0]?.name ?? ''
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

  function confirmFrame() {
    if (!frameEditing) return
    const name = frameEditing.item.name.trim()
    const others = frameNames.filter((_, i) => i !== cadFrames.length + (frameEditing.index ?? -1))
    if (!name || ['global', '전역'].includes(name) || others.includes(name)) {
      setError(
        new Error(
          !name
            ? '좌표계 이름을 입력하십시오.'
            : `‘${name}’은(는) 사용할 수 없는 좌표계 이름입니다. 전역(global) 또는 이미 존재하는 이름(도면의 좌표계 포함)과 달라야 합니다.`,
        ),
      )
      return
    }
    const item = { ...frameEditing.item, name }
    const list = [...conditionFrames]
    if (frameEditing.index === null) list.push(item)
    else list[frameEditing.index] = item
    setDraft({ ...draft, coordinate_systems: list })
    setFrameEditing(null)
    setPlacing(null)
    setError(null)
  }

  /**
   * 곡선 창의 확인 — 이름이 비었거나 겹치면 막는다. **곡선은 공유다**: 이름을 바꾸면 그것을 가리키던 하중을
   * 모든 케이스에서 함께 바꾼다(열린 하중 창의 것도).
   */
  function confirmCurve() {
    if (!curveEditing) return
    const name = curveEditing.item.name.trim()
    const list = whole.curves ?? []
    if (!name || list.some((one, i) => i !== curveEditing.index && one.name === name)) {
      setError(new Error(!name ? '곡선 이름을 입력하십시오.' : `‘${name}’ 곡선이 이미 존재합니다. 다른 이름을 입력하십시오.`))
      return
    }
    const old = curveEditing.index === null ? null : (list[curveEditing.index]?.name ?? null)
    const item = { ...curveEditing.item, name }
    const at = curveEditing.index
    setWhole((now) => {
      const base = old ? renameCurve(now, old, name) : now
      const curves = [...(base.curves ?? [])]
      if (at === null) curves.push(item)
      else curves[at] = item
      return { ...base, curves }
    })
    if (old && old !== name && editing?.item.curve === old) setEditing({ ...editing, item: { ...editing.item, curve: name } })
    setCurveEditing(null)
    setError(null)
  }

  /** 곡선을 지운다 — 가리키는 하중이 있으면 못 한다(창의 단추가 막는다). */
  function removeCurve(index: number) {
    setWhole((now) => ({ ...now, curves: (now.curves ?? []).filter((_, i) => i !== index) }))
    setCurveEditing(null)
    setError(null)
  }

  function openCurve(index: number) {
    const one = (draft.curves ?? [])[index]
    if (!one) return
    setError(null)
    setCurveEditing({ index, item: structuredClone(one) })
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

  /**
   * 담아 둔 재료의 **내보낼 단위계 값** — 트리에서 무엇이 있는지, 탄성계수가 빠지지 않았는지, 단위를 못
   * 바꾼 것이 없는지 본다. 내보낼 때와 같은 함수(서버)로 바꾸고, 재료나 단위계가 바뀔 때만 다시 묻는다.
   * 고를 때만 말하고 담은 뒤에는 조용했다(2026-11-17).
   */
  const exportSystem = draft.units?.system ?? 'mm_n_tonne'
  const materialsKey = JSON.stringify(draft.materials.map((one) => [one.ref ?? null, Object.keys(one.payload ?? {}).length]))
  const converted = useResource(
    () => (draft.materials.length > 0 ? materialsApi.converted(draft.materials.map((one) => one.payload ?? {}), exportSystem) : Promise.resolve(null)),
    [materialsKey, exportSystem],
  )

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

  /** 준비 점검 — 흩어진 ⚠ 를 한 자리에. 사양표가 오기 전에는 비어 있다. */
  const checks = useMemo(
    () =>
      schema.data
        ? readiness({
            draft,
            schema: schema.data,
            bodies: bodies.data?.items ?? null,
            converted: converted.loading ? null : (converted.data?.items ?? null),
            notes,
            geometry: problems,
            moved: loaded.moved,
            kept: loaded.kept,
          })
        : [],
    [draft, schema.data, bodies.data, converted.loading, converted.data, notes, problems, loaded],
  )
  /** 준비 점검의 줄을 눌렀다 — 트리에서 그 자리를 펼치거나 조건 창을 연다. */
  function openCheck(where: ReadinessOpen) {
    if (where.kind === 'item') return openItem(where.group, where.index)
    if (where.kind === 'curve') return openCurve(where.index)
    setTree(where)
  }

  if (schema.loading) return <Skeleton className="h-96 w-full" />
  if (schema.error) return <ErrorNotice error={schema.error} />
  const spec = schema.data!
  const system = draft.units?.system ?? 'mm_n_tonne'
  const systemOf = spec.unit_systems?.find((one) => one.key === system)
  /** 입력 단위계 — 조건의 값은 늘 이것(도면과 같은 mm · N · t)으로 적는다. 칸마다 단위를 붙인다. */
  const inputOf = spec.unit_systems?.find((one) => one.key === (spec.input_system ?? 'mm_n_tonne'))
  /** 창의 조건이 받는 선택 그룹 종류 — 3D 선택 단추를 그에 맞게 막는다. */
  const editingAccepts = editing && editing.group !== 'analysis' ? acceptsOf(editing.group, editing.item.type) : null
  const editingSpec: GroupSchema | undefined =
    editing?.group === 'analysis'
      ? {
          label: '해석 설정',
          types: (spec.analysis.properties?.type?.enum ?? []) as string[],
          fields: spec.analysis.properties ?? {},
          required: [],
          notes: spec.analysis.notes,
          intro: spec.analysis.intro,
        }
      : editing
        ? spec.groups[editing.group]
        : undefined
  /**
   * 곡선의 쓰임 단추 — 하중 칸마다 그 표를 읽는 법(가속도 PSD — 로그-로그 · g^2/Hz, 주파수별 배율 — 선형 · 단위
   * 없음). 이름표는 하중 사양표의 그 칸 이름이다.
   */
  const curvePresets: CurvePreset[] = Object.values(spec.curves?.uses ?? {})
    .filter((use, i, all) => all.findIndex((one) => one.field === use.field) === i)
    .map((use) => ({ label: spec.groups.loads?.fields[use.field]?.title ?? use.field, interpolation: use.interpolation, unit: use.unit }))
  const curveList = spec.curves ? (draft.curves ?? []) : undefined
  /** 고치는 곡선을 가리키는 하중 — 저장된 이름으로(바꾸는 중인 이름이 아니라). */
  const curveUsing =
    curveEditing && curveEditing.index !== null ? curveUsers(whole, (whole.curves ?? [])[curveEditing.index]?.name ?? '') : []

  return (
    <div className="space-y-3">
      {cases.length > 0 && (
        <CaseTabs
          cases={cases}
          active={Math.min(active, cases.length - 1)}
          locked={!!editing}
          onSelect={(index) => {
            setActive(index)
            setTree(null)
          }}
          onChange={(next, index) => {
            setWhole((now) => withCases(now, next))
            setActive(index)
          }}
        />
      )}
      {/* **리본** — 더하는 일은 여기서, 있는 것은 왼쪽 트리에서(`ConditionsRibbon`). */}
      <ConditionsRibbon
        groups={GROUP_KEYS.map((key) => ({ key, label: spec.groups[key]?.label ?? key }))}
        state={{
          dirty,
          saving,
          editing: !!editing,
          editingTakesPicks: !!editing && editingTargets.length > 0,
          grouping,
          measuring,
          showContacts,
          section: !!section,
          xray,
          partsReady: !!bodies.data,
        }}
        on={{
          onSave: () => onSave(saved(whole)),
          onToggleGrouping: () => {
            if (grouping) return closeGroup()
            clearMembers()
            setGrouping(true)
          },
          onPickMaterials: () => setPicking(true),
          onOpenParts: () => setPartsOpen(true),
          onAdd: addItem,
          onAddCurve: spec.curves
            ? () => {
                setError(null)
                setCurveEditing({ index: null, item: emptyCurve(draft.curves ?? []) })
              }
            : undefined,
          onAddFrame: () =>
            setFrameEditing({ index: null, item: { name: nextFrameName(frameNames), origin: [0, 0, 0], rotate: [0, 0, 0] } }),
          onToggleMeasuring: () => {
            if (!measuring) {
              // 재는 동안 3D 선택은 재는 데 쓴다 — 담던 선택 그룹 창은 닫는다.
              setGrouping(false)
              clearMembers()
            }
            setMeasuring(!measuring)
          },
          onToggleContacts: () => setShowContacts(!showContacts),
          onToggleSection: toggleSection,
          onToggleXray: () => setXray(!xray),
          onOpenAnalysis: () => openWindow({ group: 'analysis', index: null, item: structuredClone(draft.analysis) as ConditionItem }),
        }}
      />

      {/*
        **단위계 — 입력은 하나, 내보내기만 고른다.** 조건의 값은 늘 mm · N · t(도면과 같다)로 적고,
        점 파일을 만들 때만 고른 계로 옮긴다. 입력 계를 고르게 했더니 한 화면에 mm(도면 · 좌표계 ·
        측정)와 m(변위량 · 하중)가 섞여 「SI 를 골랐는데 왜 mm 가 보이지」 가 됐다(2026-09-28).
      */}
      <div className="bg-muted/40 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border px-3 py-1.5 text-xs">
        <Scale className="size-4" />
        <span className="font-medium">
          입력 {inputOf ? `${inputOf.length}·${inputOf.force}·${inputOf.stress}·${inputOf.mass}` : 'mm·N·MPa·tonne'}
        </span>
        <span className="text-muted-foreground">도면과 동일한 단위로 입력합니다.</span>
        <label className="ml-auto flex items-center gap-1.5 font-medium">
          내보내기 단위계
          <select
            aria-label="내보내기 단위계"
            className="bg-background rounded border px-1.5 py-0.5 text-xs"
            value={system}
            onChange={(e) => setDraft({ ...draft, units: { system: e.target.value } })}
          >
            {(spec.unit_systems ?? []).map((one) => (
              <option key={one.key} value={one.key}>
                {one.label}
              </option>
            ))}
          </select>
        </label>
        {systemOf && systemOf.key !== inputOf?.key && (
          <span className="text-muted-foreground">
            점 파일로 내보낼 때 {systemOf.length}·{systemOf.force}·{systemOf.stress} 단위로 변환합니다.
          </span>
        )}
        {defaultSystem && defaultSystem !== system && (
          <span className="text-amber-700 dark:text-amber-400">
            작업의 기본 내보내기 단위계({spec.unit_systems?.find((one) => one.key === defaultSystem)?.label ?? defaultSystem})와 다릅니다.
          </span>
        )}
      </div>

      {/*
        **준비 점검** — 흩어져 있던 ⚠(물성 · 대상 없는 조건 · 좌표 기준 그룹 · 식 · 옮긴 메시 · 도면)를 한 자리에.
        줄을 누르면 고칠 자리(트리 · 조건 창)를 연다.
      */}
      <ReadinessPanel items={checks} onOpen={openCheck} />

      {/* 접촉 점검 — 맞닿았는데 접촉이 없는 쌍, 본딩 채우기, 모달에서 접촉이 풀리는 법. */}
      <ContactCheck recipe={recipe} draft={draft} onApply={setDraft} />

      {error && <ErrorNotice error={error} />}

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
              // 다시 묻는 동안은 비운다 — 지난 답은 지금 목록과 순서가 다를 수 있다(물성을 뺀 직후).
              converted={converted.loading ? null : (converted.data?.items ?? null)}
              convertedError={converted.error}
              dictionary={converted.data?.dictionary ?? true}
              materialTemperature={materialTemperatureOf(draft.initial)}
              decks={deckChoices}
              names={names}
              groups={GROUP_KEYS.map((key) => ({
                key,
                label: spec.groups[key]?.label ?? key,
                items: draft[key] ?? [],
              }))}
              analysis={[String(draft.analysis?.type ?? ''), systemOf ? `내보내기 ${systemOf.length}·${systemOf.stress}` : '']
                .filter(Boolean)
                .join(' · ')}
              editing={editing}
              selected={tree}
              selectionCount={litCount}
              hidden={hiddenParts}
              onToggleHidden={(name) =>
                setHiddenParts((now) => (now.includes(name) ? now.filter((one) => one !== name) : [...now, name]))
              }
              onShowAll={() => setHiddenParts([])}
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
              settings={draft.body_settings ?? []}
              onOpenSettings={() => setPartsOpen(true)}
              onRemoveSelection={removeSelection}
              onOpenItem={openItem}
              onOpenAnalysis={() =>
                openWindow({ group: 'analysis', index: null, item: structuredClone(draft.analysis) as ConditionItem })
              }
              caseName={cases.length > 0 ? (cases[Math.min(active, cases.length - 1)]?.name ?? '') : undefined}
              frames={[
                ...cadFrames.map((one) => ({ name: one.name, source: 'cad' as const, index: -1 })),
                ...conditionFrames.map((one, index) => ({ name: one.name, source: 'conditions' as const, index, on: one.on })),
              ]}
              onOpenFrame={(index) => setFrameEditing({ index, item: structuredClone(conditionFrames[index]) })}
              curves={curveList}
              onOpenCurve={openCurve}
            />
          </CardContent>
        </Card>

        {/* ── 3D ── */}
        {/* `py-0` — 3D 는 칸을 통째로 쓴다. Card 의 세로 여백이 그만큼 뷰어를 깎았다. */}
        <Card className="flex min-h-0 flex-col gap-0 overflow-hidden py-0">
          <PickKindBar
            pickKind={pickKind}
            accepts={editingAccepts}
            hint={
              (pickKind === 'body' ? '면을 클릭하면 해당 바디가 선택됩니다. ' : '') +
              (editing && editingTargets.length > 0
                ? '선택한 형상이 열린 조건의 적용 대상이 됩니다(Ctrl·Shift: 다중 선택, Shift+드래그: 사각형 선택).'
                : grouping
                  ? 'Ctrl 또는 Shift로 추가하고, Shift+드래그로 사각형 영역 안의 형상을 추가합니다.'
                  : '3D에서 선택하면 선택 그룹이 생성됩니다.')
            }
            onPick={(kind) => {
              setPickKind(kind)
              // **한 그룹은 한 종류다** — 종류를 바꾸면 담아 둔 것은 비운다.
              clearMembers()
            }}
          />
          <CardContent className="relative min-h-0 flex-1 p-0">
            {showContacts && <ContactLegend counts={contactCounts} none={draft.contacts.length === 0} />}
            {section && <SectionControls section={section} range={sectionRange} onChange={setSection} />}
            <PickViewer
              mesh={mesh}
              mode="measure"
              // **켠 것 하나만.** 바디는 면을 눌러 고르므로 면과 함께 켜면 안 된다.
              measureKinds={
                placePick
                  ? { point: placing === 'point', edge: placing === 'edge', face: placing === 'face' }
                  : measuring
                  ? { point: measureKinds.has('point'), edge: measureKinds.has('edge'), face: measureKinds.has('face') }
                  : {
                      point: pickKind === 'point',
                      edge: pickKind === 'edge',
                      face: pickKind === 'face',
                      body: pickKind === 'body',
                    }
              }
              onMeasure={(pick, mods) => {
                // 좌표계를 화면에서 지정하는 중이면 누른 것이 그 좌표계의 원점(과 방향)이 된다.
                if (placePick && frameStart) {
                  const placed = framePlacement(pick, frameStart.rotate)
                  if (placed) setFrameItem(placed.origin, placed.rotate)
                  setPlacing(null)
                  return
                }
                if (!measuring) {
                  // 바디를 누르면 왼쪽 트리에서도 그 파트를 고른다 — 줄이 밝아지고 펼쳐져, 그 자리의 눈 단추로
                  // 바로 숨긴다(2026-11-17, 사용자 요청).
                  if (pick.kind === 'body') setTree({ kind: 'part', name: pick.name })
                  return void ask(pick, mods)
                }
                if (pick.kind === 'body') return
                setMeasures((now) => (now.length >= 3 ? [pick] : [...now, pick]))
              }}
              // Shift + 끌기 — 사각형 안에 온전히 든 것(가려진 것은 빼고)을 더한다. 재는 동안은 아니다.
              onBoxSelect={measuring ? undefined : (picks) => void addMany(picks)}
              // 담은 것을 번호와 함께 표시한다 — 목록의 몇 번이 어디인지. 재는 동안은 잰 것.
              measureMarks={measuring ? measureMarks(measures, kept) : marks}
              frames={frameRows}
              frameHandle={
                frameStart && (placing === 'rotate' || placing === 'translate')
                  ? { origin: frameStart.origin, rotate: frameStart.rotate, mode: placing }
                  : null
              }
              onFrameHandle={setFrameItem}
              partColors={partColors}
              // 트리에서 파트를 누르면 3D 에서도 그 파트만 또렷하게 — 어느 것에 지정하는지 보인다.
              emphasis={tree?.kind === 'part' && bodyNames.length > 1 ? tree.name : null}
              section={section}
              xray={xray}
              hiddenParts={hiddenParts}
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
            : editingAccepts
              ? `이 조건은 ${acceptsLabel(editingAccepts)}에만 적용됩니다. 3D에서 선택하면 적용 대상으로 지정됩니다(Ctrl 또는 Shift로 다중 선택).`
              : '3D에서 형상을 선택하면 적용 대상으로 지정됩니다. Ctrl 또는 Shift로 여러 형상을 함께 선택할 수 있습니다.'
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
            {/* 3D 에 비춘 것이 무엇인지 — 접촉이면 양쪽의 색. */}
            {editRefs.length > 0 && (
              <p className="text-muted-foreground flex flex-wrap items-center gap-x-3 text-xs" aria-label="적용 대상 표시">
                {contactEditing ? (
                  <>
                    <span>
                      <span className="mr-1 inline-block size-2.5 rounded-sm" style={{ background: '#dc2626' }} aria-hidden />
                      접촉면(Contact)
                    </span>
                    <span>
                      <span className="mr-1 inline-block size-2.5 rounded-sm" style={{ background: '#2563eb' }} aria-hidden />
                      대상면(Target)
                    </span>
                    <span>가려진 경우 「투명 보기」 · 「단면」 · 파트 숨기기로 확인하십시오.</span>
                  </>
                ) : (
                  <span>적용 대상이 3D에 강조되어 있습니다.</span>
                )}
              </p>
            )}
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
              frames={frameNames}
              units={inputOf}
              analysis={editing.group === 'loads' ? String(draft.analysis?.type ?? 'modal') : undefined}
              curves={editing.group === 'loads' ? curveList : undefined}
              curveUses={spec.curves?.uses}
              onMakeCurve={(curve) => setWhole((now) => ({ ...now, curves: [...(now.curves ?? []), curve] }))}
              onChange={(next) => setEditing({ ...editing, item: next })}
            />
          </>
        )}
      </FloatingWindow>

      {/* ── 좌표계 — 조건의 「좌표계」 칸이 이름으로 가리킨다. ── */}
      <FloatingWindow
        open={!!frameEditing}
        title={`좌표계 ${frameEditing?.index === null ? '추가' : '수정'}`}
        description="구속의 x·y·z가 이 좌표계의 축 방향이 됩니다. 원점·회전에 =식을 사용하거나 선택 그룹의 면에 연결하면 DOE로 치수가 변경될 때 함께 갱신됩니다."
        onClose={() => {
          setFrameEditing(null)
          setPlacing(null)
        }}
        footer={
          <>
            {frameEditing && frameEditing.index !== null && (
              <Button
                variant="ghost"
                className="sm:mr-auto"
                onClick={() => {
                  setDraft({ ...draft, coordinate_systems: conditionFrames.filter((_, i) => i !== frameEditing.index) })
                  setFrameEditing(null)
                }}
              >
                삭제
              </Button>
            )}
            <Button
              variant="ghost"
              onClick={() => {
                setFrameEditing(null)
                setPlacing(null)
              }}
            >
              취소
            </Button>
            <Button onClick={confirmFrame}>확인</Button>
          </>
        }
      >
        {frameEditing && (
          <FrameForm
            value={frameEditing.item}
            onChange={(item) => setFrameEditing({ ...frameEditing, item })}
            groups={names.filter((one) => one.entity === 'face').map((one) => one.name)}
            placing={placing}
            onPlacing={setPlacing}
          />
        )}
      </FloatingWindow>

      {/* ── 곡선 — 공유. 하중의 표 칸이 이름으로 가리킨다. ── */}
      {spec.curves && (
        <FloatingWindow
          open={!!curveEditing}
          title={`곡선 ${curveEditing?.index === null ? '추가' : '수정'}`}
          description="모든 케이스가 함께 쓰는 곡선입니다. 내보낼 때 점 × 배율을 그 곡선을 가리키는 하중의 표로 풀어 싣습니다."
          onClose={() => setCurveEditing(null)}
          footer={
            <>
              {curveEditing && curveEditing.index !== null && (
                <Button
                  variant="ghost"
                  className="sm:mr-auto"
                  disabled={curveUsing.length > 0}
                  title={curveUsing.length > 0 ? `이 곡선을 쓰는 하중이 있습니다(${curveUsing.join(', ')}). 하중에서 곡선을 먼저 떼십시오.` : undefined}
                  onClick={() => curveEditing.index !== null && removeCurve(curveEditing.index)}
                >
                  삭제
                </Button>
              )}
              <Button variant="ghost" onClick={() => setCurveEditing(null)}>
                취소
              </Button>
              <Button onClick={confirmCurve}>확인</Button>
            </>
          }
        >
          {curveEditing && (
            <CurveForm
              value={curveEditing.item}
              onChange={(item) => setCurveEditing({ ...curveEditing, item })}
              fields={spec.curves.fields}
              intro={spec.curves.intro}
              presets={curvePresets}
              users={curveUsing}
            />
          )}
        </FloatingWindow>
      )}

      {/* ── 측정 — 도면 편집기와 같은 창. 띄운 채 3D 를 누른다. ── */}
      <MeasureDialog
        open={measuring}
        picks={measures}
        kept={kept}
        kinds={measureKinds}
        onKinds={setMeasureKinds}
        onUndo={() => setMeasures((now) => now.slice(0, -1))}
        onClear={() => setMeasures([])}
        onKeep={() => {
          if (measures.length === 0) return
          setKept((list) => [...list, { id: `m-${Date.now()}`, picks: measures, label: keptLabel(measures) }])
          setMeasures([])
        }}
        onDropKept={(id) => setKept((list) => list.filter((one) => one.id !== id))}
        onClose={() => setMeasuring(false)}
      />

      {/*
        ── 선택 그룹 추가 — 리본 단추로 열거나, 창 없이 3D 를 선택하면 열린다. Ctrl(⌘)은 넣고
        빼기, Shift 는 더하기. 여럿이면 규칙들의 합으로 저장된다.
      */}
      <FloatingWindow
        open={grouping}
        title="선택 그룹 추가"
        description="3D에서 형상을 선택하십시오. Ctrl 또는 Shift를 누른 채 선택하면 여러 형상이 추가되고, Shift를 누른 채 드래그하면 사각형 영역 안에 완전히 포함된 형상이 추가됩니다. 한 그룹에는 한 종류(점, 엣지, 면, 바디)만 포함할 수 있습니다."
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

      <PartSettingsDialog
        open={partsOpen}
        onClose={() => setPartsOpen(false)}
        bodies={bodies.data?.items ?? []}
        materials={draft.materials}
        settings={draft.body_settings ?? []}
        schema={spec.body_settings}
        lengthUnit={inputOf?.length ?? 'mm'}
        onMaterialsChange={(materials) => setDraft({ ...draft, materials })}
        onSettingsChange={(body_settings) => setDraft({ ...draft, body_settings })}
        onPickMaterials={() => setPicking(true)}
      />
    </div>
  )
}

export type { NamedSelection }

/**
 * 온도별 물성을 고르는 기준 온도 — 초기조건 「환경 온도」 의 값, 없으면 22 °C(받는 쪽도 같다). 식이면 설계점마다
 * 다르니 `'formula'`.
 */
function materialTemperatureOf(initial: ConditionItem[] | undefined): number | 'formula' {
  const environment = (initial ?? []).find((one) => one.type === 'environment_temperature')
  const value = environment?.value
  if (typeof value === 'number') return value
  if (typeof value === 'string' && value.trim().startsWith('=')) return 'formula'
  if (typeof value === 'string' && value.trim() !== '' && Number.isFinite(Number(value))) return Number(value)
  return DEFAULT_MATERIAL_TEMPERATURE
}
