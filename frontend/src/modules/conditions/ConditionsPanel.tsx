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
  | { kind: 'analysis' }
  | null

/** 3D 에서 찍은 것 → 서버에 물을 말. */
function toPick(pick: MeasurePick): { what: string; point: number[]; label: string } {
  if (pick.kind === 'point') return { what: 'vertices', point: pick.at, label: '점' }
  if (pick.kind === 'edge') return { what: 'edges', point: pick.edge.midpoint, label: '엣지' }
  return { what: 'faces', point: pick.face.center, label: '면' }
}

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
      candidates.what === 'faces' ? 'face' : candidates.what === 'edges' ? 'edge' : 'vertex'
    setDraft({
      ...draft,
      named_selections: [...names, { name, entity, select: candidate.select }],
    })
    setCandidates(null)
    setChosen({ kind: 'selection', index: names.length })
  }

  function addItem(group: string) {
    const spec = schema.data?.groups[group]
    if (!spec) return
    const item: ConditionItem = { type: spec.types[0] }
    if ('name' in spec.fields) item.name = `${GROUP_ICON[group] ?? group} ${counts[group] + 1}`
    if ('on' in spec.fields) item.on = names[0]?.name ?? ''
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

      <div className="grid gap-3 lg:grid-cols-[260px_1fr_300px]">
        {/* ── 조건 목록 ── */}
        <Card>
          <CardContent className="space-y-3 p-3 text-sm">
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
                {draft.materials.map((one, index) => (
                  <li key={index} className="flex items-center gap-1 px-2 py-1">
                    <span className="truncate">{String((one.ref as Record<string, unknown>)?.name ?? '이름 없음')}</span>
                    <span className="text-muted-foreground text-xs">{String(one.apply_to ?? '전체')}</span>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="ml-auto h-6 px-1"
                      onClick={() =>
                        setDraft({ ...draft, materials: draft.materials.filter((_, i) => i !== index) })
                      }
                    >
                      ×
                    </Button>
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
                value={draft.units?.system ?? 'mm-t-s'}
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
        <Card className="min-h-[420px]">
          <CardContent className="h-[420px] p-0">
            <PickViewer
              mesh={mesh}
              mode="measure"
              measureKinds={{ point: true, edge: true, face: true }}
              onMeasure={(pick) => void ask(pick)}
              className="h-full w-full"
            />
          </CardContent>
        </Card>

        {/* ── 속성 ── */}
        <Card>
          <CardContent className="space-y-3 p-3 text-sm">
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
            ) : chosen?.kind === 'item' ? (
              <div className="space-y-2">
                <ConditionForm
                  group={spec.groups[chosen.group]}
                  item={(draft[chosen.group as keyof Conditions] as ConditionItem[])[chosen.index]}
                  names={names}
                  onChange={(next) => {
                    const list = [...(draft[chosen.group as keyof Conditions] as ConditionItem[])]
                    list[chosen.index] = next
                    setDraft({ ...draft, [chosen.group]: list })
                  }}
                />
                <Button size="sm" variant="ghost" onClick={removeChosen}>
                  지우기
                </Button>
              </div>
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

      <MaterialPicker
        open={picking}
        onClose={() => setPicking(false)}
        // 조건 한 벌이 고른 계로 보여 준다 — 검산한 값이 그대로 나가야 한다.
        system={draft.units?.system ?? 'mm-t-s'}
        onPick={(row) => {
          // **payload 통째로** 싣는다 — 「어느 것이 영률인가」 는 솔버를 아는 쪽의 일이다.
          setDraft({
            ...draft,
            materials: [
              ...draft.materials,
              {
                apply_to: '전체',
                ref: {
                  source: row.source === 'catalog' ? 'matnexus-catalog' : 'matnexus',
                  code: row.code,
                  name: row.name,
                  fetched_at: new Date().toISOString(),
                },
                payload: row.payload,
              },
            ],
          })
          setPicking(false)
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
