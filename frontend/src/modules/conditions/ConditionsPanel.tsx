/**
 * 「해석 조건」 — 작업 화면의 둘째 탭. **이것이 시뮬레이션 모드다.**
 *
 * 도면(CAD 모드)은 형상을 만들고, 여기서는 이미 있는 형상 **위에** 조건을 붙인다. 형상을 안
 * 바꾸므로 새 버전이 생기지 않는다 — 그래서 리본도 저장 고르기도 없다.
 *
 * 세로 셋: 조건 목록 · 3D · 속성.
 *
 * ## 이름표를 먼저, 조건은 그 위에
 *
 * 조건은 면을 직접 가리키지 않고 **이름표만** 가리킨다. 이름표는 좌표가 아니라 셀렉터로
 * 저장되므로(「아래쪽 면」 · 「반지름 4.25 원통면」) 실험계획이 치수를 바꿔도 설계점마다 다시
 * 풀린다. 3D 에서 찍으면 서버가 후보를 주고(`/cad/recipe/selectors`) **사람이 고른다** —
 * 하나를 자동으로 정하면 「볼트 구멍 넷」 을 원했는데 「이 구멍 하나」 가 저장되는 날이 온다.
 */

import { useEffect, useMemo, useState } from 'react'

import type { Recipe } from '@/modules/cad/api'
import { useRecipeMesh } from '@/modules/cad/useRecipeMesh'
import { ConditionForm } from '@/modules/conditions/ConditionForm'
import { materialsApi } from '@/modules/materials/api'
import { MaterialPicker } from '@/modules/materials/MaterialPicker'
import { asConditions, conditionsApi, GROUP_KEYS } from '@/modules/conditions/api'
import type {
  ConditionItem,
  Conditions,
  ConditionsSchema,
  NamedSelection,
  SelectorCandidate,
} from '@/modules/conditions/api'
import { ApiError } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
import { useFillHeight } from '@/shared/hooks/useFillHeight'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Card, CardContent } from '@/shared/components/ui/card'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { useResource } from '@/shared/hooks/useResource'
import type { MeasurePick } from '@/shared/viewer/PickViewer'
import PickViewer from '@/shared/viewer/PickViewer'

/** 지금 오른쪽에 무엇을 펼쳐 두었나. */
type Chosen =
  | { kind: 'selection'; index: number }
  | { kind: 'item'; group: string; index: number }
  | { kind: 'material'; index: number }
  | { kind: 'analysis' }
  | null

/** 3D 에서 찍은 것 → 서버에 물을 말. */
function toPick(pick: MeasurePick): { what: string; point: number[]; label: string } {
  if (pick.kind === 'point') return { what: 'vertices', point: pick.at, label: '점' }
  if (pick.kind === 'edge') return { what: 'edges', point: pick.edge.midpoint, label: '엣지' }
  if (pick.kind === 'body') return { what: 'bodies', point: [], label: '바디' }
  return { what: 'faces', point: pick.face.center, label: '면' }
}

/**
 * **무엇을 찍을 것인가.** 켠 것 하나만 잡힌다.
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

const GROUP_ICON: Record<string, string> = {
  constraints: '구속',
  loads: '하중',
  contacts: '접촉',
  initial: '초기조건',
  mesh_hints: '메시 힌트',
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
  const [chosen, setChosen] = useState<Chosen>(null)
  const [candidates, setCandidates] = useState<{
    what: string
    label: string
    list: SelectorCandidate[]
  } | null>(null)
  const [newName, setNewName] = useState('')
  const [picked, setPicked] = useState<number | null>(null)
  const [picking, setPicking] = useState(false)
  /** 지금 찍을 종류 — 하나만. 기본은 면(조건이 가장 많이 붙는 자리다). */
  const [pickKind, setPickKind] = useState<PickKind>('face')
  const [error, setError] = useState<Error | null>(null)

  const schema = useResource<ConditionsSchema>(() => conditionsApi.schema(), [])
  const { mesh, problems } = useRecipeMesh(recipe)

  useEffect(() => setDraft(asConditions(value)), [value])

  const names = draft.named_selections
  const counts = useMemo(
    () => Object.fromEntries(GROUP_KEYS.map((key) => [key, (draft[key] ?? []).length])),
    [draft],
  )

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

  function addSelection() {
    if (!candidates || picked === null) return
    const candidate = candidates.list[picked]
    const name = newName.trim() || candidate.label
    if (names.some((one) => one.name === name)) {
      setError(new Error(`「${name}」 이름표가 이미 있습니다 — 다른 이름을 쓰세요.`))
      return
    }
    const entity =
      PICK_KINDS.find((one) => one.what === candidates.what)?.entity ?? 'face'
    setDraft({
      ...draft,
      named_selections: [...names, { name, entity, select: candidate.select }],
    })
    setCandidates(null)
    setChosen({ kind: 'selection', index: names.length })
  }

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

  function addItem(group: string) {
    const spec = schema.data?.groups[group]
    if (!spec) return
    const item: ConditionItem = { type: spec.types[0] }
    if ('name' in spec.fields) item.name = `${GROUP_ICON[group] ?? group} ${counts[group] + 1}`
    if ('on' in spec.fields) item.on = namesFor(group)[0]?.name ?? ''
    const list = [...(draft[group as keyof Conditions] as ConditionItem[]), item]
    setDraft({ ...draft, [group]: list })
    setChosen({ kind: 'item', group, index: list.length - 1 })
  }

  function removeChosen() {
    if (!chosen) return
    if (chosen.kind === 'selection') {
      const gone = names[chosen.index]
      setDraft({
        ...draft,
        named_selections: names.filter((_, i) => i !== chosen.index),
        // 가리키던 조건은 남겨 두되 빈 칸이 된다 — 저장할 때 서버가 짚어 준다.
        ...Object.fromEntries(
          GROUP_KEYS.map((key) => [
            key,
            (draft[key] ?? []).map((one) =>
              one.on === gone?.name ? { ...one, on: '' } : one,
            ),
          ]),
        ),
      })
    } else if (chosen.kind === 'item') {
      const list = (draft[chosen.group as keyof Conditions] as ConditionItem[]).filter(
        (_, i) => i !== chosen.index,
      )
      setDraft({ ...draft, [chosen.group]: list })
    }
    setChosen(null)
  }

  /**
   * 세 칸이 함께 쓸 높이 — 화면 아래까지. 위쪽 줄이 바뀌면 다시 잰다.
   *
   * **조기 반환보다 위**에 있어야 한다. 아래에 두면 로딩 중 렌더와 그 뒤 렌더의 훅 수가
   * 달라져 React 가 상태를 잘못 잇는다(시험이 그걸 잡았다).
   */
  const fill = useFillHeight<HTMLDivElement>({ min: 420, gap: 8, deps: [chosen?.kind, names.length] })

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
  const bodyNames = useMemo(
    () => (bodies.data?.items ?? []).map((one) => one.name),
    [bodies.data],
  )

  if (schema.loading) return <Skeleton className="h-96 w-full" />
  if (schema.error) return <ErrorNotice error={schema.error} />
  const spec = schema.data!

  return (
    <div className="space-y-3">
      {error && <ErrorNotice error={error} />}
      {problems.length > 0 && (
        <p className="text-muted-foreground text-xs">
          도면에 문제가 있어 3D 가 안 보입니다 — 「도면」 탭에서 고치세요.
        </p>
      )}

      {/*
        **세 칸이 남은 높이를 함께 쓴다.** 3D 를 420px 로 굳혀 두면 큰 화면에서 아래가 비고,
        면을 고르려고 돌려 볼 자리가 모자란다. 옆 칸(이름표 목록 · 속성)은 길어질 수 있으므로
        **칸 안에서 스크롤**한다 — 페이지가 통째로 늘어나면 3D 가 화면 밖으로 밀린다.
      */}
      <div ref={fill.ref} style={fill.style} className="grid min-h-0 gap-3 lg:grid-cols-[260px_1fr_300px]">
        {/* ── 조건 목록 ── */}
        <Card className="min-h-0 overflow-hidden">
          <CardContent className="h-full space-y-3 overflow-y-auto p-3 text-sm">
            <div>
              <p className="mb-1 font-medium">
                이름표 <span className="text-muted-foreground">{names.length}</span>
              </p>
              {names.length === 0 && (
                <p className="text-muted-foreground text-xs">
                  3D 에서 면 · 엣지 · 점을 찍어 만드세요.
                </p>
              )}
              <ul className="space-y-1">
                {names.map((one, index) => (
                  <li key={one.name}>
                    <button
                      type="button"
                      className={`w-full rounded px-2 py-1 text-left hover:bg-muted ${
                        chosen?.kind === 'selection' && chosen.index === index ? 'bg-muted' : ''
                      }`}
                      onClick={() => setChosen({ kind: 'selection', index })}
                    >
                      {one.name}
                      <Badge variant="outline" className="ml-2">
                        {one.entity}
                      </Badge>
                    </button>
                  </li>
                ))}
              </ul>
            </div>

            <div>
              <div className="mb-1 flex items-center justify-between">
                <p className="font-medium">
                  물성 <span className="text-muted-foreground">{draft.materials.length}</span>
                </p>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-6 px-2"
                  aria-label="물성 더하기"
                  onClick={() => setPicking(true)}
                >
                  +
                </Button>
              </div>
              <ul className="space-y-1">
                {/*
                  **목록에서는 고르기만 한다.** 붙일 자리 · 솔버 덱은 편집창에서 — 줄마다
                  칸을 늘어놓으면 물성이 셋만 돼도 왼쪽이 읽을 수 없게 된다.
                */}
                {draft.materials.map((one, index) => (
                  <li key={index}>
                    <button
                      type="button"
                      className={`flex w-full items-center gap-1 rounded px-2 py-1 text-left hover:bg-muted ${
                        chosen?.kind === 'material' && chosen.index === index ? 'bg-muted' : ''
                      }`}
                      onClick={() => setChosen({ kind: 'material', index })}
                    >
                      <span className="truncate">
                        {String((one.ref as Record<string, unknown>)?.name ?? '이름 없음')}
                      </span>
                      {/* 어디에 붙였나 — 한눈에 보여야 「전체로 둔 채 잊는 것」 을 잡는다. */}
                      <Badge variant="outline" className="ml-auto shrink-0 font-normal">
                        {String(one.apply_to ?? '전체')}
                      </Badge>
                      {((one as { deck_formats?: string[] }).deck_formats ?? []).length > 0 && (
                        <Badge variant="secondary" className="shrink-0 font-normal">
                          덱 {((one as { deck_formats?: string[] }).deck_formats ?? []).length}
                        </Badge>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            </div>

            {GROUP_KEYS.map((group) => (
              <div key={group}>
                <div className="mb-1 flex items-center justify-between">
                  <p className="font-medium">
                    {spec.groups[group]?.label ?? group}{' '}
                    <span className="text-muted-foreground">{counts[group]}</span>
                  </p>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-6 px-2"
                    aria-label={`${spec.groups[group]?.label ?? group} 더하기`}
                    onClick={() => addItem(group)}
                  >
                    +
                  </Button>
                </div>
                <ul className="space-y-1">
                  {(draft[group] ?? []).map((one, index) => (
                    <li key={`${group}-${index}`}>
                      <button
                        type="button"
                        className={`w-full rounded px-2 py-1 text-left hover:bg-muted ${
                          chosen?.kind === 'item' &&
                          chosen.group === group &&
                          chosen.index === index
                            ? 'bg-muted'
                            : ''
                        }`}
                        onClick={() => setChosen({ kind: 'item', group, index })}
                      >
                        {String(one.name ?? one.type ?? '')}
                        <span className="text-muted-foreground ml-2 text-xs">
                          {String(one.on ?? '')}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}

            <button
              type="button"
              className={`w-full rounded px-2 py-1 text-left font-medium hover:bg-muted ${
                chosen?.kind === 'analysis' ? 'bg-muted' : ''
              }`}
              onClick={() => setChosen({ kind: 'analysis' })}
            >
              해석 설정
              <span className="text-muted-foreground ml-2 text-xs">
                {String(draft.analysis?.type ?? '')}
              </span>
            </button>

            {/*
              **단위계는 한 벌에 하나다.** 조건에 적힌 숫자와 물성 값이 같은 계로 풀려야
              해석이 맞는다 — MatNexus 는 밀도만 mm·t·s 로 주고 나머지는 SI 로 주므로,
              이것이 없으면 밀도는 맞고 탄성계수가 10⁶ 배 틀린 채로 나간다.
            */}
            <div className="mt-2 border-t pt-2">
              <label className="text-muted-foreground text-xs" htmlFor="단위계">
                단위계
              </label>
              <select
                id="단위계"
                className="mt-1 w-full rounded border px-2 py-1 text-sm"
                value={draft.units?.system ?? 'mm_n_tonne'}
                onChange={(e) => setDraft({ ...draft, units: { system: e.target.value } })}
              >
                {(spec.unit_systems ?? []).map((one) => (
                  <option key={one.key} value={one.key}>
                    {one.label}
                  </option>
                ))}
              </select>
              <p className="text-muted-foreground mt-1 text-xs">
                물성은 이 계로 환산해 **원본과 나란히** 내보냅니다 — 원본은 손대지 않습니다.
              </p>
            </div>
          </CardContent>
        </Card>

        {/* ── 3D ── */}
        <Card className="flex min-h-0 flex-col overflow-hidden">
          {/*
            **무엇을 찍을지 먼저 고른다.** 없을 때는 엣지를 고르려는데 점이 먼저 잡혔다 —
            뷰어가 점 · 엣지 · 면 순으로 걸고, 그 순서를 사람이 바꿀 길이 없었다.
          */}
          <div className="flex shrink-0 flex-wrap items-center gap-1 border-b px-2 py-1.5">
            <span className="text-muted-foreground mr-1 text-xs">찍을 것</span>
            {PICK_KINDS.map((one) => (
              <button
                key={one.key}
                type="button"
                aria-pressed={pickKind === one.key}
                className={`rounded border px-2 py-0.5 text-xs ${
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
              {pickKind === 'body' ? '면을 누르면 그 덩어리를 집습니다' : '3D 에서 눌러 이름표를 만듭니다'}
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
              className="h-full w-full"
            />
          </CardContent>
        </Card>

        {/* ── 속성 ── */}
        <Card className="min-h-0 overflow-hidden">
          <CardContent className="h-full space-y-3 overflow-y-auto p-3 text-sm">
            {candidates ? (
              <div className="space-y-2">
                <p className="font-medium">{candidates.label}을 찍었습니다</p>
                <p className="text-muted-foreground text-xs">
                  **좌표가 아니라 말로 저장합니다** — 치수를 바꿔도 같은 것을 가리키도록.
                </p>
                <ul className="space-y-1">
                  {candidates.list.map((one, index) => (
                    <li key={one.label}>
                      <button
                        type="button"
                        className={`w-full rounded border px-2 py-1 text-left ${
                          picked === index ? 'border-primary' : ''
                        }`}
                        onClick={() => setPicked(index)}
                      >
                        {one.label}
                        <span className="text-muted-foreground ml-2 text-xs">
                          지금 {one.matches}개
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
                <div className="space-y-1">
                  <Label htmlFor="ns-name">이름표 이름</Label>
                  <Input
                    id="ns-name"
                    value={newName}
                    placeholder={candidates.list[picked ?? 0]?.label ?? ''}
                    onChange={(e) => setNewName(e.target.value)}
                  />
                </div>
                <div className="flex gap-2">
                  <Button size="sm" onClick={addSelection}>
                    이름표 만들기
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setCandidates(null)}>
                    취소
                  </Button>
                </div>
              </div>
            ) : chosen?.kind === 'selection' ? (
              <div className="space-y-2">
                <p className="font-medium">{names[chosen.index]?.name}</p>
                <p className="text-muted-foreground text-xs">
                  {names[chosen.index]?.entity} · 셀렉터
                </p>
                <pre className="bg-muted overflow-x-auto rounded p-2 text-xs">
                  {JSON.stringify(names[chosen.index]?.select ?? {}, null, 2)}
                </pre>
                <Button size="sm" variant="ghost" onClick={removeChosen}>
                  지우기
                </Button>
              </div>
            ) : chosen?.kind === 'item' || chosen?.kind === 'material' ? (
              // 고치는 것은 **편집창**에서 — 오른쪽 칸은 3D 에서 찍은 것을 받는 자리다.
              <p className="text-muted-foreground text-xs">편집창에서 고치는 중입니다.</p>
            ) : chosen?.kind === 'analysis' ? (
              <ConditionForm
                group={{
                  label: '해석 설정',
                  types: (spec.analysis.properties?.type?.enum ?? []) as string[],
                  fields: spec.analysis.properties ?? {},
                  required: [],
                }}
                item={draft.analysis as ConditionItem}
                names={names}
                onChange={(next) => setDraft({ ...draft, analysis: next })}
              />
            ) : (
              <p className="text-muted-foreground text-xs">
                왼쪽에서 고르거나, 3D 에서 면 · 엣지 · 점을 찍어 이름표를 만드세요.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/*
        **더할 때 바로 고친다.** 예전에는 왼쪽 목록에 줄만 생기고 오른쪽 칸에서 고쳤는데,
        「구속을 더했다」 와 「무엇을 어디에 거는가」 사이가 떨어져 있어 빈 줄을 만들어 놓고
        잊는 일이 생겼다. 더하면 곧바로 물어본다.
      */}
      <Dialog
        open={chosen?.kind === 'item'}
        onOpenChange={(next) => !next && setChosen(null)}
      >
        <DialogContent className="sm:max-w-lg">
          {chosen?.kind === 'item' && (
            <>
              <DialogHeader>
                <DialogTitle>
                  {spec.groups[chosen.group]?.label ?? chosen.group} 고치기
                </DialogTitle>
                <DialogDescription>
                  종류를 고르고 값을 넣습니다. **어디에** 는 이름표로 가리킵니다 — 3D 에서
                  찍어 만든 그 이름입니다.
                </DialogDescription>
              </DialogHeader>
              <ConditionForm
                group={spec.groups[chosen.group]}
                item={(draft[chosen.group as keyof Conditions] as ConditionItem[])[chosen.index]}
                names={namesFor(chosen.group)}
                onChange={(next) => {
                  const list = [...(draft[chosen.group as keyof Conditions] as ConditionItem[])]
                  list[chosen.index] = next
                  setDraft({ ...draft, [chosen.group]: list })
                }}
              />
              <div className="flex justify-end gap-2">
                <Button size="sm" variant="ghost" onClick={removeChosen}>
                  지우기
                </Button>
                <Button size="sm" onClick={() => setChosen(null)}>
                  닫기
                </Button>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>

      {/*
        **고른 물성을 어디에 붙일지 여기서 정한다.** 예전에는 왼쪽 목록 줄에 칸을 늘어놓아
        물성이 셋만 돼도 읽을 수 없었고, 고르자마자 묻지 않아 「전체」 인 채로 두고 잊었다.
      */}
      <Dialog
        open={chosen?.kind === 'material'}
        onOpenChange={(next) => !next && setChosen(null)}
      >
        <DialogContent className="sm:max-w-lg">
          {chosen?.kind === 'material' &&
            (() => {
              const one = draft.materials[chosen.index]
              if (!one) return null
              const ref = (one.ref ?? {}) as Record<string, unknown>
              const 이름 = String(ref.name ?? '이름 없음')
              const 덱후보 = (deckChoices[String(ref.material_id ?? '')] ?? []).filter((f) => f.ready)
              const 고른덱 = (one as { deck_formats?: string[] }).deck_formats ?? []
              const 고치기 = (next: Record<string, unknown>) =>
                setDraft({
                  ...draft,
                  materials: draft.materials.map((m, i) => (i === chosen.index ? { ...m, ...next } : m)),
                })
              return (
                <>
                  <DialogHeader>
                    <DialogTitle>{이름}</DialogTitle>
                    <DialogDescription>
                      이 물성을 **어느 바디에** 붙일지 정합니다. 값은 MatNexus 가 준 그대로
                      나갑니다 — 우리가 고치지 않습니다.
                    </DialogDescription>
                  </DialogHeader>

                  <div className="space-y-1">
                    <Label htmlFor="mat-body">붙일 자리</Label>
                    <select
                      id="mat-body"
                      className="w-full rounded border px-2 py-1 text-sm"
                      value={String(one.apply_to ?? '전체')}
                      onChange={(e) => 고치기({ apply_to: e.target.value })}
                    >
                      <option value="전체">
                        전체{bodyNames.length > 1 ? ` (${bodyNames.length} 개 바디)` : ''}
                      </option>
                      {(bodies.data?.items ?? []).map((body) => (
                        <option key={body.name} value={body.name}>
                          {body.name}
                          {body.volume ? ` — ${Math.round(body.volume).toLocaleString()} mm³` : ''}
                        </option>
                      ))}
                    </select>
                    {bodyNames.length <= 1 && (
                      <p className="text-muted-foreground text-xs">
                        이 도면은 덩어리가 하나입니다 — 고를 것이 「전체」 뿐입니다.
                      </p>
                    )}
                  </div>

                  {덱후보.length > 0 && (
                    <div className="space-y-1">
                      <Label>솔버 덱 함께 보내기</Label>
                      <p className="text-muted-foreground text-xs">
                        받는 쪽이 제 덱을 손으로 짜는 대신 그대로 씁니다. 중립 물성은 그대로
                        나가고 이것은 **옆에** 붙습니다.
                      </p>
                      <div className="flex flex-wrap gap-1">
                        {덱후보.map((f) => {
                          const 켬 = 고른덱.includes(f.key)
                          return (
                            <button
                              key={f.key}
                              type="button"
                              aria-pressed={켬}
                              className={`rounded border px-2 py-0.5 text-xs ${켬 ? 'border-primary bg-accent' : 'text-muted-foreground'}`}
                              onClick={() =>
                                고치기({
                                  deck_formats: 켬
                                    ? 고른덱.filter((x) => x !== f.key)
                                    : [...고른덱, f.key],
                                })
                              }
                            >
                              {f.key}
                            </button>
                          )
                        })}
                      </div>
                    </div>
                  )}

                  <div className="flex justify-end gap-2">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        setDraft({
                          ...draft,
                          materials: draft.materials.filter((_, i) => i !== chosen.index),
                        })
                        setChosen(null)
                      }}
                    >
                      빼기
                    </Button>
                    <Button size="sm" onClick={() => setChosen(null)}>
                      닫기
                    </Button>
                  </div>
                </>
              )
            })()}
        </DialogContent>
      </Dialog>

      <MaterialPicker
        open={picking}
        onClose={() => setPicking(false)}
        // 조건 한 벌이 고른 계로 보여 준다 — 검산한 값이 그대로 나가야 한다.
        system={draft.units?.system ?? 'mm_n_tonne'}
        onPick={(row) => {
          // **payload 통째로** 싣는다 — 「어느 것이 영률인가」 는 솔버를 아는 쪽의 일이다.
          setDraft({
            ...draft,
            materials: [
              ...draft.materials,
              {
                apply_to: '전체',
                ref: {
                  source:
                    row.source === 'catalog'
                      ? 'matnexus-catalog'
                      : row.source === 'literature'
                        ? 'matnexus-literature'
                        : 'matnexus',
                  // **그쪽 id** — 덱을 뽑으려면 이것이 필요하다(번호로는 카드를 못 찾고,
                  // 문헌은 번호가 없는 것이 많다).
                  material_id: row.id,
                  code: row.code,
                  name: row.name,
                  fetched_at: new Date().toISOString(),
                },
                payload: row.payload,
              },
            ],
          })
          setPicking(false)
          // **고르자마자 「어디에」 를 묻는다** — 나중으로 미루면 「전체」 인 채로 잊는다.
          setChosen({ kind: 'material', index: draft.materials.length })
        }}
      />

      <div className="flex items-center gap-2">
        <Button onClick={() => onSave(draft)} disabled={saving}>
          조건 저장
        </Button>
        <span className="text-muted-foreground text-xs">
          도면은 바뀌지 않습니다 — 새 버전이 생기지 않아요.
        </span>
      </div>
    </div>
  )
}

export type { NamedSelection }
