/**
 * 「해석 조건」 — 작업 화면의 둘째 탭. **이것이 시뮬레이션 모드다.**
 *
 * 도면(CAD 모드)은 형상을 만들고, 여기서는 이미 있는 형상 **위에** 조건을 붙인다. 형상을 안
 * 바꾸므로 새 버전이 생기지 않는다.
 *
 * ## 도면 편집기와 같은 모양
 *
 * 위에 **리본**(더하는 단추 — 물성 · 구속 · 하중 …), 왼쪽에 **모델 구성 트리**(있는 것 —
 * 파트 · 물성 · 이름표 · 조건), 나머지는 3D 다. 부품 · 지그를 그리는 화면과 같은 자리에 같은
 * 일이 있어야 두 모드를 오갈 때 손이 헤매지 않는다.
 *
 * 조건은 **3D 를 가리지 않는 창**에서 고친다 — 창을 띄운 채 3D 에서 적용 대상을 선택하면
 * 그 조건의 대상으로 지정된다(`ConditionWindows`).
 *
 * ## 이름표를 먼저, 조건은 그 위에
 *
 * 조건은 면을 직접 가리키지 않고 **이름표만** 가리킨다. 이름표는 좌표가 아니라 셀렉터로
 * 저장되므로(「아래쪽 면」 · 「반지름 4.25 원통면」) 실험계획이 치수를 바꿔도 설계점마다 다시
 * 풀린다. 3D 에서 선택하면 서버가 후보를 주고(`/cad/recipe/selectors`) **사람이 고른다** —
 * 하나를 자동으로 정하면 「볼트 구멍 넷」 을 원했는데 「이 구멍 하나」 가 저장되는 날이 온다.
 */

import {
  Anchor,
  ArrowDownToLine,
  FlaskConical,
  Grid3x3,
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
import { CandidatePicker, FloatingWindow } from '@/modules/conditions/ConditionWindows'
import type { Candidates } from '@/modules/conditions/ConditionWindows'
import { materialColor, ModelTree, UNASSIGNED_COLOR } from '@/modules/conditions/ModelTree'
import type { TreeSelection } from '@/modules/conditions/ModelTree'
import { materialsApi } from '@/modules/materials/api'
import type { MaterialRow } from '@/modules/materials/api'
import { MaterialPicker } from '@/modules/materials/MaterialPicker'
import {
  asConditions,
  assignBody,
  conditionsApi,
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
} from '@/modules/conditions/api'
import { ApiError } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { useFillHeight } from '@/shared/hooks/useFillHeight'
import { Button } from '@/shared/components/ui/button'
import { Card, CardContent } from '@/shared/components/ui/card'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { useResource } from '@/shared/hooks/useResource'
import type { MeasurePick } from '@/shared/viewer/PickViewer'
import PickViewer from '@/shared/viewer/PickViewer'

/**
 * 창에서 고치는 조건 하나 — **확인을 눌러야 한 벌에 들어간다.** `index` 가 `null` 이면 새로
 * 더하는 것이다. 취소하면 아무것도 안 바뀐다(3D 에서 만든 이름표는 남는다 — 그것은 그것대로
 * 쓸모가 있다).
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
  { key: 'face', label: '면', entity: 'face', what: 'faces' },
  { key: 'edge', label: '엣지', entity: 'edge', what: 'edges' },
  { key: 'point', label: '점', entity: 'vertex', what: 'vertices' },
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

/** 이 묶음의 조건이 이름표를 가리키는 칸 — 접촉은 둘(원본 · 상대)이다. */
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
  /** 트리에서 펼친 것 — 파트 · 물성 · 이름표. */
  const [tree, setTree] = useState<TreeSelection>(null)
  const [editing, setEditing] = useState<Editing>(null)
  const [candidates, setCandidates] = useState<Candidates | null>(null)
  const [newName, setNewName] = useState('')
  const [picked, setPicked] = useState(0)
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
   * 그 조건이 가리킬 수 있는 이름표만.
   *
   * **초기조건은 바디에 건다** — 온도 · 속도 · 예응력은 몸 전체의 상태이지 한 면의 것이
   * 아니다. 면 이름표를 고를 수 있게 두면 해석 쪽에서야 「그 자리에 못 건다」 를 안다.
   */
  function namesFor(group: string): NamedSelection[] {
    if (group === 'initial') return names.filter((one) => one.entity === 'body')
    return names
  }

  /** 창에서 고치는 조건이 3D 선택을 받는가 — 이름표를 가리키는 칸이 있어야 한다. */
  const editingTargets = editing ? targetFields(schema.data?.groups[editing.group]) : []

  async function ask(pick: MeasurePick) {
    const { what, point, label } = toPick(pick)
    setError(null)
    // **바디는 서버에 물을 것이 없다.** 면 · 엣지 · 점은 「이 자리를 무엇으로 부를까」 를
    // 셀렉터 후보로 되받아야 하지만, 바디는 **이름이 곧 답**이다(`topology.bodies`).
    if (pick.kind === 'body') {
      setCandidates({
        what,
        label,
        list: [{ label: `바디 「${pick.name}」`, select: { body: pick.name }, matches: 1 }],
      })
      setPicked(0)
      setNewName(pick.name)
      return
    }
    try {
      const got = await conditionsApi.selectors(recipe, what, point)
      setCandidates({ what, label, list: got.candidates })
      setPicked(0)
      setNewName('')
    } catch (failure) {
      setError(failure instanceof ApiError ? failure : new Error(String(failure)))
    }
  }

  /** 고른 후보와 **같은 규칙의 이름표**가 이미 있으면 그 이름. */
  const existing = useMemo(() => {
    const candidate = candidates?.list[picked]
    if (!candidates || !candidate) return null
    const entity = PICK_KINDS.find((one) => one.what === candidates.what)?.entity ?? 'face'
    const same = names.find(
      (one) => one.entity === entity && JSON.stringify(one.select) === JSON.stringify(candidate.select),
    )
    return same?.name ?? null
  }, [candidates, picked, names])

  /**
   * 고른 후보로 이름표를 만든다 — 같은 규칙의 이름표가 있으면 새로 만들지 않고 그것을 쓴다.
   * 쓸 이름을 돌려준다(못 만들면 `null`).
   */
  function makeSelection(): { name: string; draft: Conditions } | null {
    if (!candidates) return null
    const candidate = candidates.list[picked]
    if (!candidate) return null
    if (existing) return { name: existing, draft }
    const name = newName.trim() || candidate.label
    if (names.some((one) => one.name === name)) {
      setError(new Error(`「${name}」 이름표가 이미 있습니다 — 다른 이름을 입력하세요.`))
      return null
    }
    const entity = PICK_KINDS.find((one) => one.what === candidates.what)?.entity ?? 'face'
    return { name, draft: { ...draft, named_selections: [...names, { name, entity, select: candidate.select }] } }
  }

  /** 창 없이 3D 를 선택했을 때 — 이름표만 만들고 트리에서 펼쳐 보인다. */
  function createSelection() {
    const made = makeSelection()
    if (!made) return
    setDraft(made.draft)
    setCandidates(null)
    setError(null)
    setTree({ kind: 'selection', index: made.draft.named_selections.findIndex((one) => one.name === made.name) })
  }

  /**
   * 조건 창을 띄운 채 3D 를 선택했을 때 — 이름표를 만들고 **그 조건의 대상으로 지정한다.**
   * 이름표를 따로 만들고 다시 조건으로 돌아가 목록에서 고르면 한 가지 일이 세 걸음이 된다.
   * 접촉은 원본이 비었으면 원본, 아니면 상대에 넣는다.
   */
  function assignSelection() {
    if (!editing) return
    const made = makeSelection()
    if (!made) return
    const key = editingTargets.find((one) => !editing.item[one]) ?? editingTargets[editingTargets.length - 1]
    setDraft(made.draft)
    setEditing({ ...editing, item: { ...editing.item, [key]: made.name } })
    setCandidates(null)
    setError(null)
  }

  /**
   * 창을 연다 — 초기조건이면 선택 대상을 바디로 바꾼다(바디에만 건다).
   *
   * 트리에서 펼친 파트는 접는다 — 펼친 파트만 또렷하고 나머지는 반투명이라, 그대로 두면
   * 적용 대상을 선택할 3D 가 흐리게 남는다.
   */
  function openWindow(next: NonNullable<Editing>) {
    setCandidates(null)
    setError(null)
    setTree(null)
    if (next.group === 'initial' && pickKind !== 'body') {
      pickKindBefore.current = pickKind
      setPickKind('body')
    }
    setEditing(next)
  }

  function closeWindow() {
    setEditing(null)
    setCandidates(null)
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
   * 보인다. 단품은 면에 파트 이름표가 없어 칠할 수 없고, 칠할 까닭도 없다(파트가 하나다).
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
                  setPickKind(one.key)
                  // 종류를 바꾸면 고르던 후보는 뜻을 잃는다.
                  setCandidates(null)
                }}
              >
                {one.label}
              </button>
            ))}
            <span className="text-muted-foreground ml-auto text-xs">
              {editing && editingTargets.length > 0
                ? '3D 에서 선택하면 열린 조건의 적용 대상으로 지정됩니다'
                : pickKind === 'body'
                  ? '면을 클릭하면 해당 바디가 선택됩니다'
                  : '3D 에서 클릭하여 이름표를 생성합니다'}
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
              onMeasure={(pick) => void ask(pick)}
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
              : '3D 에서 형상을 선택하면 적용 대상으로 지정됩니다.'
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
            {candidates && editingTargets.length > 0 && (
              <CandidatePicker
                candidates={candidates}
                picked={picked}
                onPicked={setPicked}
                name={newName}
                onName={setNewName}
                existing={existing}
                confirmLabel="적용 대상으로 지정"
                onConfirm={assignSelection}
                onCancel={() => setCandidates(null)}
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

      {/* ── 창 없이 3D 를 선택했을 때 — 이름표 생성 ── */}
      <FloatingWindow
        open={!!candidates && (!editing || editingTargets.length === 0)}
        title="이름표 생성"
        onClose={() => setCandidates(null)}
        // 해석 설정 창과 함께 뜨는 드문 경우 겹치지 않게 조금 아래에 세운다.
        className={editing ? 'top-56' : 'top-24'}
      >
        {candidates && (
          <CandidatePicker
            candidates={candidates}
            picked={picked}
            onPicked={setPicked}
            name={newName}
            onName={setNewName}
            existing={existing}
            confirmLabel="이름표 생성"
            onConfirm={createSelection}
            onCancel={() => setCandidates(null)}
          />
        )}
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
