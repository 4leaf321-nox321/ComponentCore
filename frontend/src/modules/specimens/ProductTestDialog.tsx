/**
 * **제품에 시험 규격 적용** — 정하중 · 방향 하중 · 손잡이·벽걸이 · 압착 · 적층 압축 · 수압 · 비틀림 ·
 * 등가 가속도 · 진동 · 고유진동수. 내 부품
 * 작업이나 공용 부품을 골라, 그 레시피를 그대로 쓴 새 작업에 시험 변수 · 하중 자리 · 구속 · 하중 ·
 * 해석 설정을 붙인다. 제품의 물성은 따라온다.
 *
 * 기본 자리는 받침이 아랫면(-Z), 하중이 윗면(+Z)이다. **3D 에서 면을 고르면** 그 면이 고정 면 ·
 * 누를 면 · 비트는 끝이 된다 — 「고르기」 를 누르면 제품을 띄우고(그때 한 번 서버가 그린다), 면을
 * 누르면 담고 다시 누르면 뺀다. 고른 점 · 법선 · 면 종류를 보내면 서버가 「이 방향을 보는 면 중
 * 이 점에서 가장 가까운 것」 으로 적는다.
 */

import { lazy, Suspense, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { kindOf } from '@/modules/specimens/kinds'
import type { Slot } from '@/modules/specimens/kinds'
import { partsApi } from '@/modules/parts/api'
import { specimensApi } from '@/modules/specimens/api'
import type { FacePick, FaceSlot, PresetRow, ProductPreset } from '@/modules/specimens/api'
import { worksApi } from '@/modules/works/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { useResource } from '@/shared/hooks/useResource'
import type { MeasureMarks, MeasurePick, MeshData } from '@/shared/viewer/PickViewer'

const PickViewer = lazy(() => import('@/shared/viewer/PickViewer'))

const SELECT = 'bg-background h-9 w-full rounded-md border px-2 text-sm'

const number = (text: string) => (text.trim() && Number.isFinite(Number(text)) ? Number(text) : null)

/** 방향 하중의 방향 — 고른 면에서 바깥으로(당김) · 안으로(누름) · 좌표축. */
const DIRECTIONS: { value: string; label: string; vector?: [number, number, number] }[] = [
  { value: 'pull', label: '고른 면에서 바깥으로 (당김)' },
  { value: 'push', label: '고른 면 안쪽으로 (누름)' },
  { value: '+x', label: '+X', vector: [1, 0, 0] },
  { value: '-x', label: '-X', vector: [-1, 0, 0] },
  { value: '+y', label: '+Y', vector: [0, 1, 0] },
  { value: '-y', label: '-Y', vector: [0, -1, 0] },
  { value: '+z', label: '+Z', vector: [0, 0, 1] },
  { value: '-z', label: '-Z', vector: [0, 0, -1] },
]

/** 고른 면 하나 — 보내는 것(점 · 법선 · 종류)과 3D 에 칠할 면 번호. */
type Picked = FacePick & { index: number }

/** 이 규격이 무엇을 하는지 한 줄. */
export function productSummary(preset: ProductPreset): string {
  return kindOf(preset.test)?.summary(preset) ?? ''
}

const round = (value: number) => Math.round(value * 1000) / 1000
const triple = (values: number[]) => [round(values[0] ?? 0), round(values[1] ?? 0), round(values[2] ?? 0)] as [number, number, number]

function SlotRow({ slot, picked, active, onPick, onClear }: { slot: Slot; picked: Picked[]; active: boolean; onPick: () => void; onClear: () => void }) {
  const state = picked.length > 0 ? `면 ${picked.length}개` : slot.fallback ? `비우면 ${slot.fallback}` : '꼭 고르십시오'
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <span className="min-w-20 font-medium">{slot.label}</span>
      <span className={picked.length === 0 && !slot.fallback ? 'text-destructive text-xs' : 'text-muted-foreground text-xs'}>{state}</span>
      <Button type="button" size="sm" variant={active ? 'default' : 'outline'} className="ml-auto" onClick={onPick}>
        {active ? '고르는 중' : `${slot.label} 고르기`}
      </Button>
      {picked.length > 0 && (
        <Button type="button" size="sm" variant="ghost" onClick={onClear}>
          비우기
        </Button>
      )}
    </div>
  )
}

export function ProductTestDialog({ row, onClose }: { row: PresetRow<ProductPreset>; onClose: () => void }) {
  const navigate = useNavigate()
  const preset = row.preset
  const spec = kindOf(preset.test)
  const slots = spec?.slots?.(preset) ?? []
  const works = useResource(() => worksApi.list(0, 100), [])
  const parts = useResource(() => partsApi.list(0, 100), [])
  const [source, setSource] = useState('')
  const [x, setX] = useState('')
  const [y, setY] = useState('')
  const [z, setZ] = useState('')
  const [axis, setAxis] = useState('')
  const [mass, setMass] = useState('')
  const [way, setWay] = useState('pull')
  const [name, setName] = useState('')
  const [folder, setFolder] = useState('')
  const [picks, setPicks] = useState<Partial<Record<FaceSlot, Picked[]>>>({})
  const [active, setActive] = useState<FaceSlot | null>(null)
  const [mesh, setMesh] = useState<MeshData | null>(null)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const mine = (works.data?.items ?? []).filter((one) => one.kind === 'part' && one.current_version > 0)
  const shared = parts.data?.items ?? []
  const force = preset.test === 'force'
  const loadPicked = (picks.load ?? []).length > 0
  const missing = slots.filter((one) => !one.fallback && (picks[one.slot] ?? []).length === 0)
  const needsMass = preset.test === 'compression'
  const directed = preset.test === 'directed'
  const first = (picks.load ?? [])[0]
  // 당김 · 누름은 고른 면의 법선에서 — 곡면은 법선이 자리마다 달라 좌표축을 고르게 한다.
  const vector = DIRECTIONS.find((one) => one.value === way)?.vector ?? (first && first.kind === 'plane' ? (way === 'push' ? (first.normal.map((one) => -one) as [number, number, number]) : first.normal) : null)
  const curvedWithoutAxis = directed && first !== undefined && first.kind !== 'plane' && !DIRECTIONS.find((one) => one.value === way)?.vector

  function choose(next: string) {
    setSource(next)
    setPicks({})
    setActive(null)
    setMesh(null)
  }

  async function pickInto(slot: FaceSlot) {
    if (active === slot) return setActive(null)
    setActive(slot)
    if (mesh || !source) return
    setLoading(true)
    setError(null)
    try {
      const seen = await specimensApi.productMesh(source)
      setMesh(seen.mesh ?? null)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('제품의 형상을 불러오지 못했습니다.'))
    } finally {
      setLoading(false)
    }
  }

  function onMeasure(pick: MeasurePick) {
    if (!active || pick.kind !== 'face') return
    const face = pick.face
    const one: Picked = { index: face.index, point: triple(face.center), normal: triple(face.normal), kind: face.kind }
    const single = slots.find((slot) => slot.slot === active)?.single
    setPicks((before) => {
      const current = before[active] ?? []
      const had = current.some((picked) => picked.index === one.index)
      const next = had ? current.filter((picked) => picked.index !== one.index) : single ? [one] : [...current, one]
      return { ...before, [active]: next }
    })
  }

  const marks: MeasureMarks = {
    points: [],
    segments: [],
    labels: [],
    edges: [],
    faces: Object.entries(picks).flatMap(([slot, list]) =>
      (list ?? []).flatMap((picked) => {
        const face = mesh?.faces.find((one) => one.index === picked.index)
        return face ? [{ vertices: face.vertices, triangles: face.triangles, tone: slot === active ? ('live' as const) : ('kept' as const) }] : []
      }),
    ),
  }

  async function apply() {
    setBusy(true)
    setError(null)
    try {
      const faces = Object.fromEntries(Object.entries(picks).map(([slot, list]) => [slot, (list ?? []).map(({ point, normal, kind }) => ({ point, normal, kind }))]))
      const work = await specimensApi.applyProductTest({
        preset_id: row.id,
        source,
        x: force ? number(x) : null,
        y: force ? number(y) : null,
        z: force && loadPicked ? number(z) : null,
        axis: axis ? (axis as 'x' | 'y' | 'z') : preset.test === 'vibration' || preset.test === 'acceleration' ? 'z' : null,
        faces,
        mass: needsMass ? number(mass) : null,
        direction: directed ? vector : null,
        name: name.trim() || undefined,
        folder: folder.trim(),
      })
      navigate(`/works/${work.id}`)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류가 발생했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && !busy && onClose()}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>제품에 적용</DialogTitle>
          <DialogDescription>
            ‘{row.name}’: {productSummary(preset)} 제품의 레시피와 물성을 그대로 사용한 새 작업을 생성합니다.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-1">
          <Label htmlFor="test-source">제품</Label>
          <select id="test-source" className={SELECT} value={source} onChange={(event) => choose(event.target.value)}>
            <option value="">제품을 선택하십시오</option>
            <optgroup label="내 작업의 부품">
              {mine.map((one) => (
                <option key={one.id} value={`work:${one.id}`}>
                  {one.name} (v{one.current_version})
                </option>
              ))}
            </optgroup>
            <optgroup label="공용 부품">
              {shared.map((one) => (
                <option key={one.id} value={`part:${one.id}`}>
                  {one.name} (v{one.current_version})
                </option>
              ))}
            </optgroup>
          </select>
        </div>
        {force && (
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1">
              <Label htmlFor="test-x">누르는 위치 X (mm)</Label>
              <Input id="test-x" type="number" step="any" value={x} placeholder={loadPicked ? '고른 점' : '가운데'} onChange={(event) => setX(event.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="test-y">누르는 위치 Y (mm)</Label>
              <Input id="test-y" type="number" step="any" value={y} placeholder={loadPicked ? '고른 점' : '가운데'} onChange={(event) => setY(event.target.value)} />
            </div>
            {loadPicked && (
              <div className="space-y-1">
                <Label htmlFor="test-z">누르는 위치 Z (mm)</Label>
                <Input id="test-z" type="number" step="any" value={z} placeholder="고른 점" onChange={(event) => setZ(event.target.value)} />
              </div>
            )}
          </div>
        )}
        {preset.test === 'vibration' && (
          <div className="space-y-1">
            <Label htmlFor="test-axis">가진 축</Label>
            <select id="test-axis" className={SELECT} value={axis || 'z'} onChange={(event) => setAxis(event.target.value)}>
              <option value="z">Z축</option>
              <option value="x">X축</option>
              <option value="y">Y축</option>
            </select>
          </div>
        )}
        {preset.test === 'acceleration' && (
          <div className="space-y-1">
            <Label htmlFor="test-axis">가속 방향</Label>
            <select id="test-axis" className={SELECT} value={axis || 'z'} onChange={(event) => setAxis(event.target.value)}>
              <option value="z">Z축</option>
              <option value="x">X축</option>
              <option value="y">Y축</option>
            </select>
          </div>
        )}
        {directed && (
          <div className="space-y-1">
            <Label htmlFor="test-direction">하중 방향</Label>
            <select id="test-direction" className={SELECT} value={way} onChange={(event) => setWay(event.target.value)}>
              {DIRECTIONS.map((one) => (
                <option key={one.value} value={one.value}>
                  {one.label}
                </option>
              ))}
            </select>
            <p className="text-muted-foreground text-xs">모멘트는 이 방향을 축으로 오른손 방향으로 돕니다.</p>
            {curvedWithoutAxis && <p className="text-destructive text-xs">곡면을 골랐으면 좌표축 방향을 고르십시오.</p>}
          </div>
        )}
        {preset.test === 'torsion' && (
          <div className="space-y-1">
            <Label htmlFor="test-axis">비틀림 축</Label>
            <select id="test-axis" className={SELECT} value={axis} onChange={(event) => setAxis(event.target.value)}>
              <option value="">가장 긴 축</option>
              <option value="x">X축</option>
              <option value="y">Y축</option>
              <option value="z">Z축</option>
            </select>
          </div>
        )}
        {needsMass && (
          <div className="space-y-1">
            <Label htmlFor="test-mass">제품 무게 (kg)</Label>
            <Input id="test-mass" type="number" step="any" min="0" value={mass} onChange={(event) => setMass(event.target.value)} />
          </div>
        )}
        {slots.length > 0 && (
          <div className="space-y-2 rounded-md border p-3">
            <p className="text-muted-foreground text-xs">
              면을 고르려면 「고르기」를 누른 뒤 3D에서 면을 누르십시오. 같은 면을 다시 누르면 뺍니다.
            </p>
            {slots.map((slot) => (
              <SlotRow
                key={slot.slot}
                slot={slot}
                picked={picks[slot.slot] ?? []}
                active={active === slot.slot}
                onPick={() => void pickInto(slot.slot)}
                onClear={() => setPicks({ ...picks, [slot.slot]: [] })}
              />
            ))}
            {active && !source && <p className="text-destructive text-xs">먼저 제품을 선택하십시오.</p>}
            {active && loading && <p className="text-muted-foreground text-xs">제품의 형상을 불러오는 중…</p>}
            {active && mesh && (
              <Suspense fallback={null}>
                <PickViewer mesh={mesh} mode="measure" measureKinds={{ face: true }} measureMarks={marks} onMeasure={onMeasure} className="h-72 w-full rounded-md border" />
              </Suspense>
            )}
          </div>
        )}
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label htmlFor="test-name">작업 이름</Label>
            <Input id="test-name" value={name} placeholder="제품 이름 — 규격 이름" onChange={(event) => setName(event.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="test-folder">폴더</Label>
            <Input id="test-folder" value={folder} onChange={(event) => setFolder(event.target.value)} />
          </div>
        </div>
        {spec && <p className="text-muted-foreground text-xs">{spec.hint}</p>}
        <ErrorNotice error={error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            취소
          </Button>
          <Button onClick={() => void apply()} disabled={busy || !source || missing.length > 0 || (needsMass && !number(mass)) || curvedWithoutAxis}>
            {busy ? '생성 중…' : '생성'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
