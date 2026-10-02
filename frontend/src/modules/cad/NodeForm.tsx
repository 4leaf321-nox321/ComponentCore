/** 피처 하나의 칸들 — `recipeSpec` 의 FieldSpec 을 그린다. 스케치의 도형은 SketchCanvas 가 맡는다. */

import { useState } from 'react'

import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/components/ui/select'
import { cadApi } from '@/modules/cad/api'
import type { CutList } from '@/modules/cad/api'
import { NumberField } from '@/modules/cad/NumberField'
import { GLOBAL_AXES, OP_BY_NAME, PLANE_OPTIONS, nodeKind } from '@/modules/cad/recipeSpec'
import type { FieldSpec, RecipeNode } from '@/modules/cad/recipeSpec'

/** 비워도 되는 숫자 칸 — 비우면 null(관통 · 표에서 채움). */
const NULLABLE = new Set(['depth', 'diameter', 'counter_diameter', 'counter_depth'])


/** 치수를 어느 자리에 맞출까 — 축마다 「작은 쪽 · 가운데 · 큰 쪽」. 한쪽을 고정하고 늘릴 때. */
const ALIGN_NAMES = ['min', 'center', 'max'] as const
const ALIGN_LABEL: Record<string, string> = { min: '작은 쪽', center: '가운데', max: '큰 쪽' }

function AlignInput({ value, size, onChange }: { value: unknown; size: 2 | 3; onChange: (next: string[]) => void }) {
  const current = Array.isArray(value) ? (value as string[]) : Array(size).fill('center')
  const labels = ['X', 'Y', 'Z']
  return (
    <div className={`grid gap-1 ${size === 2 ? 'grid-cols-2' : 'grid-cols-3'}`}>
      {Array.from({ length: size }, (_, i) => (
        <div key={i} className="flex items-center gap-1">
          <span className="text-muted-foreground w-3 text-xs">{labels[i]}</span>
          <Select
            value={current[i] ?? 'center'}
            onValueChange={(next) => {
              const list = [...current]
              list[i] = next
              onChange(list)
            }}
          >
            <SelectTrigger className="h-8 flex-1 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ALIGN_NAMES.map((name) => (
                <SelectItem key={name} value={name}>
                  {ALIGN_LABEL[name]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      ))}
    </div>
  )
}

function NumberInput(props: Parameters<typeof NumberField>[0]) {
  return <NumberField {...props} />
}

function VectorInput({
  value,
  size,
  onChange,
  params,
  onCreateParam,
}: {
  value: unknown
  size: 2 | 3
  params?: Record<string, number>
  onCreateParam?: (name: string, value: number) => void
  /** 변수 식(`"=L - 15"`)이 섞일 수 있다 — 자리도 변수로 잡는다. */
  onChange: (next: (number | string)[]) => void
}) {
  const current = Array.isArray(value) ? (value as (number | string)[]) : Array(size).fill(0)
  const labels = ['X', 'Y', 'Z']
  return (
    <div className={`grid gap-1 ${size === 2 ? 'grid-cols-2' : 'grid-cols-3'}`}>
      {Array.from({ length: size }, (_, i) => (
        <div key={i} className="flex items-center gap-1">
          <span className="text-muted-foreground w-3 text-xs">{labels[i]}</span>
          <NumberInput
            params={params}
            onCreateParam={onCreateParam}
            aria-label={labels[i]}
            value={current[i] ?? 0}
            onChange={(v) => {
              const next = [...current]
              next[i] = v ?? 0
              onChange(next)
            }}
          />
        </div>
      ))}
    </div>
  )
}

/** 프레임 단면 — 종류마다 칸이 다르다(서버 `schema.FrameProfile`). */
const PROFILE_TYPES: { value: string; label: string; fields: [string, string][]; seed: Record<string, number> }[] = [
  { value: 't_slot', label: '알루미늄 프로파일 (T 슬롯)', fields: [['size', '계열 (20 · 30 · 40 · 45)']], seed: { size: 40 } },
  { value: 'square_tube', label: '각관', fields: [['width', '폭'], ['thickness', '벽 두께']], seed: { width: 40, thickness: 2 } },
  { value: 'rect_tube', label: '사각관', fields: [['width', '폭'], ['height', '높이'], ['thickness', '벽 두께']], seed: { width: 60, height: 30, thickness: 2 } },
  { value: 'round_tube', label: '원관', fields: [['diameter', '바깥 지름'], ['thickness', '벽 두께']], seed: { diameter: 34, thickness: 2 } },
  { value: 'round_bar', label: '환봉', fields: [['diameter', '지름']], seed: { diameter: 20 } },
  { value: 'flat_bar', label: '평철 · 각재', fields: [['width', '폭'], ['height', '높이']], seed: { width: 50, height: 6 } },
  { value: 'angle', label: '앵글 (L)', fields: [['width', '가로 다리'], ['height', '세로 다리'], ['thickness', '두께']], seed: { width: 40, height: 40, thickness: 4 } },
  { value: 'channel', label: '채널 (ㄷ)', fields: [['width', '플랜지 폭'], ['height', '웨브 높이'], ['thickness', '두께']], seed: { width: 40, height: 80, thickness: 5 } },
  { value: 'h_beam', label: 'H 형강', fields: [['width', '플랜지 폭'], ['height', '높이'], ['web', '웨브 두께'], ['flange', '플랜지 두께']], seed: { width: 100, height: 100, web: 6, flange: 8 } },
]

function ProfileInput({
  value,
  onChange,
  params,
  onCreateParam,
}: {
  value: unknown
  onChange: (next: Record<string, unknown>) => void
  params?: Record<string, number>
  onCreateParam?: (name: string, value: number) => void
}) {
  const profile = (value ?? {}) as Record<string, unknown>
  const kind = PROFILE_TYPES.find((one) => one.value === profile.type) ?? PROFILE_TYPES[0]
  return (
    <div className="space-y-1">
      <Select value={kind.value} onValueChange={(v) => onChange({ type: v, ...PROFILE_TYPES.find((one) => one.value === v)?.seed })}>
        <SelectTrigger className="h-8" aria-label="단면 종류">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {PROFILE_TYPES.map((one) => (
            <SelectItem key={one.value} value={one.value}>
              {one.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <div className="grid grid-cols-2 gap-1">
        {kind.fields.map(([key, label]) => (
          <label key={key} className="space-y-0.5 text-xs">
            <span className="text-muted-foreground">{label} (mm)</span>
            <NumberInput aria-label={`단면 ${label}`} params={params} onCreateParam={onCreateParam} value={profile[key]} onChange={(v) => onChange({ ...profile, [key]: v ?? 0 })} />
          </label>
        ))}
      </div>
    </div>
  )
}

/** 프레임 경로 여럿 — 경로마다 점 목록. 「닫기」 는 처음 점을 끝에 다시 넣는다(닫힌 틀). */
function PathsInput({
  value,
  onChange,
  params,
  onCreateParam,
}: {
  value: unknown
  onChange: (next: unknown[][]) => void
  params?: Record<string, number>
  onCreateParam?: (name: string, value: number) => void
}) {
  const paths = (Array.isArray(value) ? value : []) as unknown[][]
  const put = (i: number, next: unknown[]) => onChange(paths.map((one, j) => (j === i ? next : one)))
  return (
    <div className="space-y-2">
      {paths.map((path, i) => {
        const first = JSON.stringify(path[0])
        const closed = path.length > 2 && JSON.stringify(path[path.length - 1]) === first
        return (
          <div key={i} className="space-y-1 rounded border p-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium">
                경로 {i + 1} — 부재 {Math.max(path.length - 1, 0)} 개{closed ? ' · 닫힘' : ''}
              </span>
              <button type="button" className="text-muted-foreground px-1 hover:text-destructive" onClick={() => onChange(paths.filter((_, j) => j !== i))} aria-label={`경로 ${i + 1} 지우기`}>
                ×
              </button>
            </div>
            {path.map((point, k) => (
              <div key={k} className="flex items-center gap-1">
                <VectorInput
                  params={params}
                  onCreateParam={onCreateParam}
                  value={point}
                  size={3}
                  onChange={(v) => put(i, path.map((one, m) => (m === k ? v : one)))}
                />
                <button type="button" className="text-muted-foreground px-1 text-xs hover:text-destructive" onClick={() => put(i, path.filter((_, m) => m !== k))} aria-label="점 지우기">
                  ×
                </button>
              </div>
            ))}
            <div className="flex gap-3 text-xs">
              <button
                type="button"
                className="text-muted-foreground hover:underline"
                onClick={() => {
                  const last = (path[path.length - 1] as number[] | undefined) ?? [0, 0, 0]
                  put(i, [...path, [Number(last[0]) + 100 || 100, Number(last[1]) || 0, Number(last[2]) || 0]])
                }}
              >
                + 점
              </button>
              {!closed && path.length > 2 && (
                <button type="button" className="text-muted-foreground hover:underline" onClick={() => put(i, [...path, path[0]])}>
                  처음 점으로 닫기
                </button>
              )}
            </div>
          </div>
        )
      })}
      <button
        type="button"
        className="text-muted-foreground text-xs hover:underline"
        onClick={() =>
          onChange([
            ...paths,
            [
              [0, 0, 0],
              [0, 0, 300],
            ],
          ])
        }
      >
        + 경로 (기둥 하나부터)
      </button>
    </div>
  )
}

/** 구조 프레임의 **절단 목록** — 서버가 부재마다 자를 길이 · 각 · 부피를 잰다. 표와 CSV. */
function CutListPanel({ node, nodes, params }: { node: RecipeNode; nodes: RecipeNode[]; params?: Record<string, number> }) {
  const [list, setList] = useState<CutList | null>(null)
  const [trouble, setTrouble] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const csv = (got: CutList) =>
    ['경로,부재,길이(mm),시작 각(°),끝 각(°),부피(mm³)', ...got.items.map((one) => [one.path, one.member, one.length, one.start_cut, one.end_cut, one.volume].join(','))].join('\n')
  return (
    <div className="space-y-1 text-xs">
      <button
        type="button"
        className="underline"
        onClick={async () => {
          setTrouble(null)
          try {
            setList(await cadApi.cutList({ params: params ?? {}, nodes }, node.id))
          } catch (failure) {
            setTrouble(failure instanceof Error ? failure.message : '절단 목록을 받지 못했습니다')
          }
        }}
      >
        절단 목록 보기
      </button>
      {trouble && <p className="text-destructive">{trouble}</p>}
      {list && (
        <div className="space-y-1">
          <p className="text-muted-foreground">
            {list.profile} · 부재 {list.count} 개 · 합계 {list.total_length.toLocaleString()} mm · 부피 {list.total_volume.toLocaleString()} mm³ (질량 = 부피 x 밀도)
          </p>
          <table className="w-full text-right">
            <thead className="text-muted-foreground">
              <tr>
                <th className="text-left">경로-부재</th>
                <th>길이</th>
                <th>시작 각</th>
                <th>끝 각</th>
              </tr>
            </thead>
            <tbody>
              {list.items.map((one) => (
                <tr key={`${one.path}-${one.member}`}>
                  <td className="text-left">
                    {one.path}-{one.member}
                  </td>
                  <td>{one.length}</td>
                  <td>{one.start_cut ? `${one.start_cut}°` : '직각'}</td>
                  <td>{one.end_cut ? `${one.end_cut}°` : '직각'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <button
            type="button"
            className="text-muted-foreground underline"
            onClick={async () => {
              await navigator.clipboard?.writeText(csv(list))
              setCopied(true)
            }}
          >
            {copied ? 'CSV 를 복사했습니다' : 'CSV 복사'}
          </button>
        </div>
      )}
    </div>
  )
}

type Bend = { at?: unknown; radius?: unknown; toward?: string; until?: string; angle?: unknown }

/** 굽힘 목록 — 줄마다 「어디서 · 반지름 · 어느 쪽 · 어디까지」. 앞에서부터 차례로 접는다. */
function BendsInput({
  value,
  onChange,
  params,
  onCreateParam,
}: {
  value: unknown
  onChange: (next: Bend[]) => void
  params?: Record<string, number>
  onCreateParam?: (name: string, value: number) => void
}) {
  const bends = Array.isArray(value) ? (value as Bend[]) : []
  const put = (i: number, patch: Bend) => onChange(bends.map((one, j) => (j === i ? { ...one, ...patch } : one)))
  const last = bends[bends.length - 1]
  return (
    <div className="space-y-2">
      {bends.map((bend, i) => (
        <div key={i} className="space-y-1 rounded border p-2">
          <div className="flex items-center justify-between text-xs">
            <span className="font-medium">굽힘 {i + 1}</span>
            <button type="button" className="text-muted-foreground px-1 hover:text-destructive" onClick={() => onChange(bends.filter((_, j) => j !== i))} aria-label="지우기">
              ×
            </button>
          </div>
          <div className="grid grid-cols-2 gap-1">
            <label className="space-y-0.5 text-xs">
              <span className="text-muted-foreground">시작 자리 (펼친 판의 좌표, mm)</span>
              <NumberInput aria-label={`굽힘 ${i + 1} 시작 자리`} params={params} onCreateParam={onCreateParam} value={bend.at} onChange={(v) => put(i, { at: v ?? 0 })} />
            </label>
            <label className="space-y-0.5 text-xs">
              <span className="text-muted-foreground">안쪽 반지름 (mm)</span>
              <NumberInput aria-label={`굽힘 ${i + 1} 반지름`} params={params} onCreateParam={onCreateParam} value={bend.radius} step={0.5} onChange={(v) => put(i, { radius: v ?? 1 })} />
            </label>
            <label className="space-y-0.5 text-xs">
              <span className="text-muted-foreground">어느 쪽으로</span>
              <Select value={bend.toward ?? 'up'} onValueChange={(v) => put(i, { toward: v })}>
                <SelectTrigger className="h-8">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="up">위로 (판의 위쪽)</SelectItem>
                  <SelectItem value="down">아래로</SelectItem>
                </SelectContent>
              </Select>
            </label>
            <label className="space-y-0.5 text-xs">
              <span className="text-muted-foreground">어디까지</span>
              <Select value={bend.until ?? 'angle'} onValueChange={(v) => put(i, { until: v })}>
                <SelectTrigger className="h-8">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="angle">각도만큼</SelectItem>
                  <SelectItem value="end">끝까지 감기</SelectItem>
                </SelectContent>
              </Select>
            </label>
          </div>
          {(bend.until ?? 'angle') === 'angle' ? (
            <label className="block space-y-0.5 text-xs">
              <span className="text-muted-foreground">굽힘 각 (도)</span>
              <NumberInput aria-label={`굽힘 ${i + 1} 각`} params={params} onCreateParam={onCreateParam} value={bend.angle ?? 90} step={5} onChange={(v) => put(i, { angle: v ?? 90 })} />
            </label>
          ) : (
            <p className="text-muted-foreground text-xs">남은 판을 이 반지름으로 끝까지 감습니다 — 각도는 남은 길이가 정합니다.</p>
          )}
        </div>
      ))}
      <button
        type="button"
        className="text-muted-foreground text-xs hover:underline"
        onClick={() =>
          onChange([
            ...bends,
            {
              at: typeof last?.at === 'number' ? last.at + 30 : 0,
              radius: last?.radius ?? 5,
              toward: 'up',
              until: 'angle',
              angle: 90,
            },
          ])
        }
      >
        + 굽힘 추가
      </button>
    </div>
  )
}

function RefSelect({
  value,
  candidates,
  onChange,
  placeholder,
}: {
  value: string
  candidates: RecipeNode[]
  onChange: (next: string) => void
  placeholder: string
}) {
  return (
    <Select value={value || '__none__'} onValueChange={(v) => onChange(v === '__none__' ? '' : v)}>
      <SelectTrigger className="h-8">
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="__none__">(고르세요)</SelectItem>
        {candidates.map((one) => (
          <SelectItem key={one.id} value={one.id}>
            {one.label ? `${one.label} (${one.id})` : one.id}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

/** 규칙으로 고르기 — `recipe_find` 의 질의를 JSON 으로. DOE 가 치수를 바꿔도 다시 찾는다. */
function RuleInput({
  value,
  what,
  onChange,
  bare = false,
}: {
  value: unknown
  what: 'edges' | 'faces'
  onChange: (next: Record<string, unknown>) => void
  /** 칸의 값이 질의 그 자체(`{kind: …}`)인가 — 아니면 `{query: …}` 로 싼다. */
  bare?: boolean
}) {
  const query = (bare ? (value as Record<string, unknown> | null) : (value as { query?: Record<string, unknown> } | null)?.query) ?? {}
  const [text, setText] = useState(JSON.stringify(query))
  const [trouble, setTrouble] = useState<string | null>(null)
  return (
    <div className="space-y-1 text-xs">
      <Input
        aria-label="규칙 (recipe_find 질의)"
        className={`h-8 font-mono text-xs ${trouble ? 'border-destructive' : ''}`}
        value={text}
        onChange={(event) => {
          setText(event.target.value)
          try {
            const parsed = JSON.parse(event.target.value) as unknown
            if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('객체여야 합니다')
            setTrouble(null)
            onChange(bare ? (parsed as Record<string, unknown>) : { query: parsed as Record<string, unknown> })
          } catch (failure) {
            setTrouble(failure instanceof Error ? failure.message : '읽을 수 없습니다')
          }
        }}
      />
      <p className={trouble ? 'text-destructive' : 'text-muted-foreground'}>
        {trouble
          ? `JSON 이 아닙니다 — ${trouble}`
          : what === 'edges'
            ? '예: {"kind":"circle","radius":5} · {"of_face":{"normal":[0,0,1]}} — 치수를 바꿔도 다시 찾습니다.'
            : '예: {"normal":[0,0,1]} · {"kind":"cylinder","radius":5} — 치수를 바꿔도 다시 찾습니다.'}
      </p>
    </div>
  )
}

const isRule = (value: unknown): boolean => typeof value === 'object' && value !== null && 'query' in value

/** 축 칸 — 원점을 지나는 X · Y · Z, 또는 앞의 기준축. */
function AxisRefSelect({ value, axes, optional, onChange }: { value: unknown; axes: RecipeNode[]; optional?: boolean; onChange: (next: string | null) => void }) {
  return (
    <Select value={value == null || value === '' ? '__none__' : String(value)} onValueChange={(v) => onChange(v === '__none__' ? null : v)}>
      <SelectTrigger className="h-8">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {optional && <SelectItem value="__none__">(없음)</SelectItem>}
        {[...GLOBAL_AXES].map((name) => (
          <SelectItem key={name} value={name}>
            원점의 {name} 축
          </SelectItem>
        ))}
        {axes.map((one) => (
          <SelectItem key={one.id} value={one.id}>
            기준축 {one.label ? `${one.label} (${one.id})` : one.id}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

/** 평면 칸(이름) — 원점을 지나는 평면, 또는 앞의 기준면. */
function PlaneRefSelect({ value, planes, onChange }: { value: unknown; planes: RecipeNode[]; onChange: (next: string) => void }) {
  return (
    <Select value={String(value ?? 'XY')} onValueChange={onChange}>
      <SelectTrigger className="h-8">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {PLANE_OPTIONS.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            원점의 {o.label} 평면
          </SelectItem>
        ))}
        {planes.map((one) => (
          <SelectItem key={one.id} value={one.id}>
            기준면 {one.label ? `${one.label} (${one.id})` : one.id}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

type DatumWay = 'vector' | 'through' | 'points' | 'plane' | 'geometry'

/** 기준을 **정하는 법** — 하나만 쓴다(서버가 둘을 섞으면 거절한다). 바꾸면 다른 방법의 칸을 지운다. */
function datumWay(node: RecipeNode): DatumWay {
  if (node.target != null || node.select != null) return 'geometry'
  if (node.op === 'datum_axis') return node.through != null ? 'through' : 'vector'
  return node.points != null ? 'points' : 'plane'
}

const DATUM_KEYS = ['origin', 'direction', 'through', 'points', 'plane', 'target', 'select']

function switchDatum(node: RecipeNode, way: DatumWay, solids: RecipeNode[]): RecipeNode {
  const next: RecipeNode = { ...node }
  for (const key of DATUM_KEYS) delete next[key]
  if (way === 'vector') Object.assign(next, { origin: [0, 0, 0], direction: [0, 0, 1] })
  if (way === 'through') next.through = [[0, 0, 0], [0, 0, 10]]
  if (way === 'points') next.points = [[0, 0, 0], [10, 0, 0], [0, 10, 0]]
  if (way === 'plane') next.plane = { name: 'XY', origin: [0, 0, 0] }
  if (way === 'geometry') {
    next.target = solids[solids.length - 1]?.id ?? ''
    next.select = node.op === 'datum_axis' ? { what: 'faces', kind: 'cylinder' } : { what: 'faces', kind: 'plane', normal: [0, 0, 1] }
  }
  return next
}

function DatumFields({
  node,
  solids,
  onChange,
  onPick,
  params,
  onCreateParam,
}: {
  node: RecipeNode
  solids: RecipeNode[]
  onChange: (next: RecipeNode) => void
  onPick?: () => void
  params?: Record<string, number>
  onCreateParam?: (name: string, value: number) => void
}) {
  const axis = node.op === 'datum_axis'
  const way = datumWay(node)
  const ways: [DatumWay, string][] = axis
    ? [
        ['vector', '점과 방향'],
        ['through', '두 점'],
        ['geometry', '형상에서 (구멍의 축 · 직선 엣지)'],
      ]
    : [
        ['plane', '이름 있는 평면 · 원점'],
        ['points', '세 점'],
        ['geometry', '형상의 평면에서'],
      ]
  const vector = (key: string, label: string, value: unknown, put: (v: (number | string)[]) => void) => (
    <div key={key} className="space-y-0.5">
      <span className="text-muted-foreground text-xs">{label}</span>
      <VectorInput params={params} onCreateParam={onCreateParam} value={value} size={3} onChange={put} />
    </div>
  )
  const list = (key: string) => (node[key] as unknown[] | undefined) ?? []
  return (
    <div className="space-y-2">
      <Select value={way} onValueChange={(v) => onChange(switchDatum(node, v as DatumWay, solids))}>
        <SelectTrigger className="h-8" aria-label="정하는 법">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {ways.map(([value, label]) => (
            <SelectItem key={value} value={value}>
              {label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {way === 'vector' && [
        vector('origin', '지나는 점', node.origin, (v) => onChange({ ...node, origin: v })),
        vector('direction', '방향', node.direction, (v) => onChange({ ...node, direction: v })),
      ]}
      {(way === 'through' || way === 'points') &&
        list(way).map((point, i) =>
          vector(`${way}-${i}`, `점 ${i + 1}`, point, (v) => {
            const next = [...list(way)]
            next[i] = v
            onChange({ ...node, [way]: next })
          }),
        )}
      {way === 'plane' && (
        <div className="space-y-1">
          <Select
            value={String((node.plane as { name?: string })?.name ?? 'XY')}
            onValueChange={(v) => onChange({ ...node, plane: { ...(node.plane as object), name: v } })}
          >
            <SelectTrigger className="h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PLANE_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {vector('plane-origin', '원점', (node.plane as { origin?: number[] })?.origin ?? [0, 0, 0], (v) =>
            onChange({ ...node, plane: { ...(node.plane as object), origin: v } }),
          )}
        </div>
      )}
      {way === 'geometry' && (
        <div className="space-y-1 text-xs">
          <RefSelect value={String(node.target ?? '')} candidates={solids} onChange={(v) => onChange({ ...node, target: v })} placeholder="대상 입체" />
          <p className="text-muted-foreground font-mono break-all">{JSON.stringify(node.select)}</p>
          <p className="text-muted-foreground">
            {axis ? '원통면(구멍 · 축)을 누르면 그 축이 됩니다.' : '평면을 누르면 그 면이 됩니다.'} 위치(near)로 고른 면을 치수가 바뀌어도
            다시 찾습니다.
          </p>
          {onPick && (
            <button type="button" className="underline" onClick={onPick}>
              3D 에서 {axis ? '원통면' : '평면'} 고르기
            </button>
          )}
        </div>
      )}
    </div>
  )
}

export function NodeForm({
  node,
  nodes,
  onChange,
  onPickFaces,
  params,
  onCreateParam,
}: {
  node: RecipeNode
  /** 레시피 전체 — 이 피처보다 **앞의** 것만 참조 후보가 된다. */
  nodes: RecipeNode[]
  onChange: (next: RecipeNode) => void
  /** 3D 에서 면을 고르게 한다(쉘의 open · 구멍의 plane). 편집기가 모달을 닫고 3D 를 넘긴다. */
  onPickFaces?: (fieldKey: string) => void
  /** 레시피의 변수 — 칸에 쓴 식의 **지금 값**을 옆에 보여 준다. */
  params?: Record<string, number>
  /** 칸에서 바로 변수를 만든다 — 변수 상자까지 가지 않아도 되게. */
  onCreateParam?: (name: string, value: number) => void
}) {
  const spec = OP_BY_NAME[node.op]
  const index = nodes.findIndex((n) => n.id === node.id)
  const before = nodes.slice(0, index)
  const candidatesFor = (field: FieldSpec) =>
    before.filter((n) => field.refKind === 'any' || !field.refKind || nodeKind(n, nodes) === field.refKind)

  function set(key: string, value: unknown) {
    onChange({ ...node, [key]: value })
  }

  if (!spec) return <p className="text-destructive text-sm">모르는 연산: {node.op}</p>

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label htmlFor="node-id" className="text-xs">
            id
          </Label>
          <Input id="node-id" value={node.id} onChange={(e) => set('id', e.target.value)} className="h-8 font-mono text-xs" />
        </div>
        <div className="space-y-1">
          <Label htmlFor="node-label" className="text-xs">
            이름
          </Label>
          <Input id="node-label" value={node.label ?? ''} onChange={(e) => set('label', e.target.value)} className="h-8" placeholder="사람이 보는 이름" />
        </div>
      </div>
      <p className="text-muted-foreground text-xs">{spec.help}</p>

      {spec.fields
        .filter((field) => field.kind !== 'shapes')
        .map((field) => (
          <div key={field.key} className="space-y-1">
            <Label htmlFor={`node-${field.key}`} className="text-xs">
              {field.label}
            </Label>
            {field.kind === 'number' && (
              <NumberInput
                id={`node-${field.key}`}
                aria-label={field.label}
                params={params}
                onCreateParam={onCreateParam}
                value={node[field.key]}
                step={field.step}
                nullable={NULLABLE.has(field.key) || field.optional === true}
                onChange={(v) => set(field.key, v)}
              />
            )}
            {(field.kind === 'align3' || field.kind === 'align2') && (
              <AlignInput
                value={node[field.key]}
                size={field.kind === 'align3' ? 3 : 2}
                onChange={(v) => set(field.key, v)}
              />
            )}
            {field.kind === 'text' && (
              <Input id={`node-${field.key}`} value={String(node[field.key] ?? '')} onChange={(e) => set(field.key, e.target.value)} className="h-8 font-mono text-xs" />
            )}
            {field.kind === 'checkbox' && (
              <input type="checkbox" checked={Boolean(node[field.key])} onChange={(e) => set(field.key, e.target.checked)} />
            )}
            {field.kind === 'select' && field.key === 'edges' && (
              <div className="space-y-1">
                <Select
                  value={isRule(node.edges) ? '__rule__' : typeof node.edges === 'object' ? '__near__' : String(node.edges ?? 'all')}
                  onValueChange={(v) => set('edges', v === '__near__' ? { near: [], tolerance: 1 } : v === '__rule__' ? { query: { kind: 'line' } } : v)}
                >
                  <SelectTrigger className="h-8">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(field.options ?? []).map((o) => (
                      <SelectItem key={o.value} value={o.value}>
                        {o.label}
                      </SelectItem>
                    ))}
                    <SelectItem value="__near__">3D 에서 고른 엣지</SelectItem>
                    <SelectItem value="__rule__">규칙으로 (치수가 바뀌어도 찾는다)</SelectItem>
                  </SelectContent>
                </Select>
                {isRule(node.edges) && <RuleInput value={node.edges} what="edges" onChange={(v) => set('edges', v)} />}
                {typeof node.edges === 'object' && !isRule(node.edges) && (
                  <p className="text-muted-foreground text-xs">
                    오른쪽 3D 에서 엣지를 누르세요 — 고른 것 {((node.edges as { near: number[][] }).near ?? []).length} 개.
                    위치로 기억하므로 형상을 조금 고쳐도 같은 자리를 찾습니다.
                  </p>
                )}
              </div>
            )}
            {field.kind === 'select' && field.key !== 'edges' && (
              <Select
                value={node[field.key] == null ? '__none__' : String(node[field.key])}
                onValueChange={(v) => set(field.key, v === '__none__' ? null : v)}
              >
                <SelectTrigger className="h-8">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(field.options ?? []).map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            {field.kind === 'xy' && (
              <VectorInput params={params} onCreateParam={onCreateParam} value={node[field.key]} size={2} onChange={(v) => set(field.key, v)} />
            )}
            {field.kind === 'xyz' && (
              <VectorInput params={params} onCreateParam={onCreateParam} value={node[field.key]} size={3} onChange={(v) => set(field.key, v)} />
            )}
            {field.kind === 'ref' && (
              <RefSelect
                value={String(node[field.key] ?? '')}
                candidates={candidatesFor(field)}
                onChange={(v) => set(field.key, v || (field.optional ? null : ''))}
                placeholder={field.label}
              />
            )}
            {field.kind === 'refs' && (
              <div className="space-y-1">
                {candidatesFor(field).map((one) => {
                  const chosen = Array.isArray(node[field.key]) && (node[field.key] as string[]).includes(one.id)
                  return (
                    <label key={one.id} className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={chosen}
                        onChange={(e) => {
                          const current = Array.isArray(node[field.key]) ? (node[field.key] as string[]) : []
                          set(field.key, e.target.checked ? [...current, one.id] : current.filter((id) => id !== one.id))
                        }}
                      />
                      {one.label ? `${one.label} (${one.id})` : one.id}
                    </label>
                  )
                })}
                {candidatesFor(field).length === 0 && <p className="text-muted-foreground text-xs">앞에 고를 피처가 없습니다.</p>}
              </div>
            )}
            {field.kind === 'axisref' && (
              <AxisRefSelect
                value={node[field.key]}
                axes={before.filter((n) => n.op === 'datum_axis')}
                optional={field.optional}
                onChange={(v) => set(field.key, v)}
              />
            )}
            {field.kind === 'planeref' && (
              <PlaneRefSelect value={node[field.key]} planes={before.filter((n) => n.op === 'datum_plane')} onChange={(v) => set(field.key, v)} />
            )}
            {(field.kind === 'datumaxis' || field.kind === 'datumplane') && (
              <DatumFields
                node={node}
                solids={before.filter((n) => nodeKind(n, nodes) === 'solid')}
                onChange={onChange}
                onPick={onPickFaces ? () => onPickFaces('datum') : undefined}
                params={params}
                onCreateParam={onCreateParam}
              />
            )}
            {field.kind === 'profile' && (
              <ProfileInput params={params} onCreateParam={onCreateParam} value={node[field.key]} onChange={(v) => set(field.key, v)} />
            )}
            {field.kind === 'paths' && <CutListPanel node={node} nodes={nodes} params={params} />}
            {field.kind === 'paths' && (
              <PathsInput params={params} onCreateParam={onCreateParam} value={node[field.key]} onChange={(v) => set(field.key, v)} />
            )}
            {field.kind === 'query' && <RuleInput bare value={node[field.key]} what="faces" onChange={(v) => set(field.key, v)} />}
            {field.kind === 'bends' && (
              <BendsInput params={params} onCreateParam={onCreateParam} value={node[field.key]} onChange={(v) => set(field.key, v)} />
            )}
            {(field.kind === 'points' || field.kind === 'points3') && (
              <div className="space-y-1">
                {(((node[field.key] as (number | string)[][]) ?? []) as (number | string)[][]).map((point, i) => (
                  <div key={i} className="flex items-center gap-1">
                    <VectorInput
                      params={params}
                      onCreateParam={onCreateParam}
                      value={point}
                      size={field.kind === 'points3' ? 3 : 2}
                      onChange={(v) => {
                        const next = [...(node[field.key] as (number | string)[][])]
                        next[i] = v
                        set(field.key, next)
                      }}
                    />
                    <button
                      type="button"
                      className="text-muted-foreground px-1 text-xs hover:text-destructive"
                      onClick={() => set(field.key, (node[field.key] as (number | string)[][]).filter((_, j) => j !== i))}
                      aria-label="지우기"
                    >
                      ×
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  className="text-muted-foreground text-xs hover:underline"
                  onClick={() => set(field.key, [...((node[field.key] as number[][]) ?? []), field.kind === 'points3' ? [0, 0, 0] : [0, 0]])}
                >
                  + {field.kind === 'points3' ? '점' : '위치'} 추가
                </button>
              </div>
            )}
            {field.kind === 'facepicks' && isRule(node[field.key]) && (
              <div className="space-y-1">
                <RuleInput value={node[field.key]} what="faces" onChange={(v) => set(field.key, v)} />
                <button type="button" className="text-muted-foreground text-xs underline" onClick={() => set(field.key, 'none')}>
                  비우기
                </button>
              </div>
            )}
            {field.kind === 'facepicks' && !isRule(node[field.key]) && (
              <div className="space-y-1 text-xs">
                <p className="text-muted-foreground">
                  고른 면 {typeof node[field.key] === 'object' && node[field.key] !== null ? ((node[field.key] as { near: number[][] }).near ?? []).length : 0} 개 — 누른
                  자리로 기억합니다.
                </p>
                <div className="flex gap-2">
                  {onPickFaces && (
                    <button type="button" className="underline" onClick={() => onPickFaces(field.key)}>
                      3D 에서 고르기
                    </button>
                  )}
                  <button type="button" className="text-muted-foreground underline" onClick={() => set(field.key, { query: { normal: [0, 0, 1] } })}>
                    규칙으로
                  </button>
                  {typeof node[field.key] === 'object' && node[field.key] !== null && (
                    <button type="button" className="text-muted-foreground underline" onClick={() => set(field.key, 'none')}>
                      비우기
                    </button>
                  )}
                </div>
              </div>
            )}
            {field.kind === 'faceselect' && (
              <div className="space-y-1">
                <Select
                  value={isRule(node[field.key]) ? '__rule__' : typeof node[field.key] === 'object' && node[field.key] !== null ? '__near__' : String(node[field.key] ?? 'top')}
                  onValueChange={(v) => set(field.key, v === '__near__' ? { near: [], tolerance: 1 } : v === '__rule__' ? { query: { normal: [0, 0, 1] } } : v)}
                >
                  <SelectTrigger className="h-8">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="top">윗면</SelectItem>
                    <SelectItem value="bottom">바닥면</SelectItem>
                    <SelectItem value="none">없음 (닫힌 속 빈 덩어리)</SelectItem>
                    <SelectItem value="__near__">3D 에서 고른 면</SelectItem>
                    <SelectItem value="__rule__">규칙으로 (치수가 바뀌어도 찾는다)</SelectItem>
                  </SelectContent>
                </Select>
                {isRule(node[field.key]) && <RuleInput value={node[field.key]} what="faces" onChange={(v) => set(field.key, v)} />}
                {typeof node[field.key] === 'object' && node[field.key] !== null && !isRule(node[field.key]) && (
                  <p className="text-muted-foreground text-xs">
                    고른 면 {((node[field.key] as { near: number[][] }).near ?? []).length} 개 — 이 창을 닫고 3D 에서 면을 누르세요.
                    {onPickFaces && (
                      <button type="button" className="ml-2 underline" onClick={() => onPickFaces(field.key)}>
                        3D 에서 고르기
                      </button>
                    )}
                  </p>
                )}
              </div>
            )}
            {field.kind === 'holeplane' && (
              <div className="text-xs">
                {(node.plane as { normal?: number[] } | null)?.normal ? (
                  <p>
                    면 위 — 원점 ({((node.plane as { origin: number[] }).origin ?? []).map((v) => v.toFixed(1)).join(', ')}), 법선 (
                    {((node.plane as { normal: number[] }).normal ?? []).map((v) => v.toFixed(2)).join(', ')})
                    <button type="button" className="ml-2 underline" onClick={() => set('plane', null)}>
                      윗면으로 되돌리기
                    </button>
                  </p>
                ) : (
                  <p className="text-muted-foreground">윗면(+Z)에서 아래로 뚫습니다.</p>
                )}
                {onPickFaces && (
                  <button type="button" className="text-muted-foreground underline" onClick={() => onPickFaces('plane')}>
                    3D 에서 뚫을 면 고르기
                  </button>
                )}
              </div>
            )}
            {field.kind === 'plane' && typeof (node.plane as { datum?: string } | null)?.datum === 'string' && (
              <div className="space-y-1 text-xs">
                <p>기준면 「{(node.plane as { datum: string }).datum}」 — 그 면이 움직이면 따라갑니다.</p>
                <button type="button" className="text-muted-foreground hover:underline" onClick={() => set('plane', { name: 'XY', origin: [0, 0, 0] })}>
                  이름 있는 평면으로 바꾸기
                </button>
              </div>
            )}
            {field.kind === 'plane' && !(node.plane as { datum?: string } | null)?.datum && (node.plane as { normal?: number[] })?.normal && (
              <div className="space-y-1 text-xs">
                <p>
                  면 위 평면 — 법선 ({((node.plane as { normal: number[] }).normal ?? []).map((v) => v.toFixed(2)).join(', ')})
                </p>
                <Label className="text-muted-foreground text-xs">원점</Label>
                <VectorInput
                  value={(node.plane as { origin?: number[] })?.origin ?? [0, 0, 0]}
                  size={3}
                  onChange={(v) => set('plane', { ...(node.plane as object), origin: v })}
                />
                <button type="button" className="text-muted-foreground hover:underline" onClick={() => set('plane', { name: 'XY', origin: [0, 0, 0] })}>
                  이름 있는 평면으로 바꾸기
                </button>
              </div>
            )}
            {field.kind === 'plane' && !(node.plane as { datum?: string } | null)?.datum && !(node.plane as { normal?: number[] })?.normal && (
              <div className="space-y-1">
                <Select
                  value={String((node.plane as { name?: string })?.name ?? 'XY')}
                  onValueChange={(v) => set('plane', v.startsWith('datum:') ? { datum: v.slice(6) } : { ...(node.plane as object), name: v })}
                >
                  <SelectTrigger className="h-8">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PLANE_OPTIONS.map((o) => (
                      <SelectItem key={o.value} value={o.value}>
                        {o.label}
                      </SelectItem>
                    ))}
                    {before
                      .filter((n) => n.op === 'datum_plane')
                      .map((one) => (
                        <SelectItem key={one.id} value={`datum:${one.id}`}>
                          기준면 {one.label ? `${one.label} (${one.id})` : one.id}
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
                <Label className="text-muted-foreground text-xs">원점</Label>
                <VectorInput
                  value={(node.plane as { origin?: number[] })?.origin ?? [0, 0, 0]}
                  size={3}
                  onChange={(v) => set('plane', { ...(node.plane as object), origin: v })}
                />
                {onPickFaces && (
                  <button type="button" className="text-muted-foreground text-xs underline" onClick={() => onPickFaces('plane')}>
                    3D 에서 면 고르기 — 그 면이 평면이 됩니다
                  </button>
                )}
              </div>
            )}
          </div>
        ))}
    </div>
  )
}
