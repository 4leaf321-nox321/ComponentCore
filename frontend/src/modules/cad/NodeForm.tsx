/** 피처 하나의 칸들 — `recipeSpec` 의 FieldSpec 을 그린다. 스케치의 도형은 SketchCanvas 가 맡는다. */

import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/components/ui/select'
import { OP_BY_NAME, PLANE_OPTIONS, nodeKind } from '@/modules/cad/recipeSpec'
import type { FieldSpec, RecipeNode } from '@/modules/cad/recipeSpec'

/** 비워도 되는 숫자 칸 — 비우면 null(관통 · 표에서 채움). */
const NULLABLE = new Set(['depth', 'diameter', 'counter_diameter', 'counter_depth'])

function num(value: unknown): string {
  return value === null || value === undefined ? '' : String(value)
}

function NumberInput({
  value,
  onChange,
  step = 0.5,
  nullable = false,
  id,
}: {
  value: unknown
  onChange: (next: number | null) => void
  step?: number
  nullable?: boolean
  id?: string
}) {
  return (
    <Input
      id={id}
      type="number"
      step={step}
      value={num(value)}
      onChange={(event) => {
        const raw = event.target.value
        if (raw === '') onChange(nullable ? null : 0)
        else onChange(Number(raw))
      }}
      className="h-8"
    />
  )
}

function VectorInput({
  value,
  size,
  onChange,
}: {
  value: unknown
  size: 2 | 3
  onChange: (next: number[]) => void
}) {
  const current = Array.isArray(value) ? (value as number[]) : Array(size).fill(0)
  const labels = ['X', 'Y', 'Z']
  return (
    <div className={`grid gap-1 ${size === 2 ? 'grid-cols-2' : 'grid-cols-3'}`}>
      {Array.from({ length: size }, (_, i) => (
        <div key={i} className="flex items-center gap-1">
          <span className="text-muted-foreground w-3 text-xs">{labels[i]}</span>
          <NumberInput
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

export function NodeForm({
  node,
  nodes,
  onChange,
  onPickFaces,
}: {
  node: RecipeNode
  /** 레시피 전체 — 이 피처보다 **앞의** 것만 참조 후보가 된다. */
  nodes: RecipeNode[]
  onChange: (next: RecipeNode) => void
  /** 3D 에서 면을 고르게 한다(쉘의 open · 구멍의 plane). 편집기가 모달을 닫고 3D 를 넘긴다. */
  onPickFaces?: (fieldKey: string) => void
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
                value={node[field.key]}
                step={field.step}
                nullable={NULLABLE.has(field.key)}
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
                  value={typeof node.edges === 'object' ? '__near__' : String(node.edges ?? 'all')}
                  onValueChange={(v) => set('edges', v === '__near__' ? { near: [], tolerance: 1 } : v)}
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
                  </SelectContent>
                </Select>
                {typeof node.edges === 'object' && (
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
            {field.kind === 'xy' && <VectorInput value={node[field.key]} size={2} onChange={(v) => set(field.key, v)} />}
            {field.kind === 'xyz' && <VectorInput value={node[field.key]} size={3} onChange={(v) => set(field.key, v)} />}
            {field.kind === 'ref' && (
              <RefSelect value={String(node[field.key] ?? '')} candidates={candidatesFor(field)} onChange={(v) => set(field.key, v)} placeholder={field.label} />
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
            {field.kind === 'points' && (
              <div className="space-y-1">
                {((node[field.key] as number[][]) ?? []).map((point, i) => (
                  <div key={i} className="flex items-center gap-1">
                    <VectorInput
                      value={point}
                      size={2}
                      onChange={(v) => {
                        const next = [...(node[field.key] as number[][])]
                        next[i] = v
                        set(field.key, next)
                      }}
                    />
                    <button
                      type="button"
                      className="text-muted-foreground px-1 text-xs hover:text-destructive"
                      onClick={() => set(field.key, (node[field.key] as number[][]).filter((_, j) => j !== i))}
                      aria-label="지우기"
                    >
                      ×
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  className="text-muted-foreground text-xs hover:underline"
                  onClick={() => set(field.key, [...((node[field.key] as number[][]) ?? []), [0, 0]])}
                >
                  + 위치 추가
                </button>
              </div>
            )}
            {field.kind === 'faceselect' && (
              <div className="space-y-1">
                <Select
                  value={typeof node[field.key] === 'object' && node[field.key] !== null ? '__near__' : String(node[field.key] ?? 'top')}
                  onValueChange={(v) => set(field.key, v === '__near__' ? { near: [], tolerance: 1 } : v)}
                >
                  <SelectTrigger className="h-8">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="top">윗면</SelectItem>
                    <SelectItem value="bottom">바닥면</SelectItem>
                    <SelectItem value="none">없음 (닫힌 속 빈 덩어리)</SelectItem>
                    <SelectItem value="__near__">3D 에서 고른 면</SelectItem>
                  </SelectContent>
                </Select>
                {typeof node[field.key] === 'object' && node[field.key] !== null && (
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
            {field.kind === 'plane' && (node.plane as { normal?: number[] })?.normal && (
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
            {field.kind === 'plane' && !(node.plane as { normal?: number[] })?.normal && (
              <div className="space-y-1">
                <Select
                  value={String((node.plane as { name?: string })?.name ?? 'XY')}
                  onValueChange={(v) => set('plane', { ...(node.plane as object), name: v })}
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
                <Label className="text-muted-foreground text-xs">원점</Label>
                <VectorInput
                  value={(node.plane as { origin?: number[] })?.origin ?? [0, 0, 0]}
                  size={3}
                  onChange={(v) => set('plane', { ...(node.plane as object), origin: v })}
                />
              </div>
            )}
          </div>
        ))}
    </div>
  )
}
