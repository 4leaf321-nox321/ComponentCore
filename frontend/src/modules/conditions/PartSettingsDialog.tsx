/**
 * 파트별 설정 — **파트마다 한 줄인 표.** 물성 · 거동 · 표현 · 해석 제외 · 메시를 한 화면에서 고친다.
 *
 * 트리에서 파트를 하나씩 열고 닫으면 파트가 열 개일 때 지친다. 표는 무엇이 남았는지 한눈에
 * 보이고, 맨 위 「모든 파트」 줄이 열 하나를 한꺼번에 바꾼다(지그 전부 강체 · 요소 2 mm).
 *
 * 고친 것은 바로 조건 초안에 들어가고 저장은 리본의 「조건 저장」 이 한다 — 트리와 같다.
 * 열 이름 · 선택지 · 설명은 서버 사양표(`body_settings`)가 준다.
 */

import { ALL_BODIES, assignBody, materialsOn, settingOf, withSetting } from '@/modules/conditions/api'
import type { Body, BodySetting, ConditionsSchema, FieldSchema, MaterialItem } from '@/modules/conditions/api'
import { NumberText } from '@/modules/conditions/NumberText'
import { Button } from '@/shared/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/components/ui/dialog'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/shared/components/ui/table'

/** 값이 파트마다 다를 때 「모든 파트」 줄이 보이는 자리. */
const MIXED = '__mixed__'

type Choice = { value: string; label: string }

/** 사양표의 선택지 — 사람 이름(`labels`)이 있으면 그것으로. */
function choicesOf(field: FieldSchema | undefined): Choice[] {
  return (field?.enum ?? []).map((value) => ({ value, label: field?.labels?.[value] ?? value }))
}

const nameOf = (material: MaterialItem | undefined) =>
  String(((material?.ref ?? {}) as Record<string, unknown>).name ?? '이름 없음')

/** `12` → 12, `=식` → 그대로, 빈칸 → 비움(국부 메시 ‘전체’ 또는 해석 플랫폼 기본값). */
function sizeOf(text: string): number | string | null {
  if (text.trim() === '') return null
  if (text.startsWith('=')) return text
  const num = Number(text)
  return Number.isFinite(num) ? num : text
}

/** 여럿의 값이 모두 같으면 그 값, 아니면 `MIXED`. */
function common(values: string[]): string {
  return values.length > 0 && values.every((one) => one === values[0]) ? values[0] : MIXED
}

const selectClass = 'bg-background h-8 w-full rounded-md border px-1.5 text-xs disabled:opacity-50'

function Select({
  label,
  value,
  choices,
  disabled,
  mixedLabel,
  onChange,
}: {
  label: string
  value: string
  choices: Choice[]
  disabled?: boolean
  /** 값이 갈렸을 때 보이는 말 — 「모든 파트」 줄은 「혼합」, 물성이 둘 붙은 파트는 「물성 중복」. */
  mixedLabel?: string
  onChange: (next: string) => void
}) {
  return (
    <select aria-label={label} className={selectClass} value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
      {mixedLabel && value === MIXED && <option value={MIXED}>{mixedLabel}</option>}
      {choices.map((one) => (
        <option key={one.value} value={one.value}>
          {one.label}
        </option>
      ))}
    </select>
  )
}

export function PartSettingsDialog({
  open,
  onClose,
  bodies,
  materials,
  settings,
  schema,
  lengthUnit = 'mm',
  onMaterialsChange,
  onSettingsChange,
  onPickMaterials,
}: {
  open: boolean
  onClose: () => void
  bodies: Body[]
  materials: MaterialItem[]
  settings: BodySetting[]
  schema: ConditionsSchema['body_settings']
  /** 요소 크기 칸의 단위 — 입력 단위계의 길이(mm). */
  lengthUnit?: string
  onMaterialsChange: (next: MaterialItem[]) => void
  onSettingsChange: (next: BodySetting[]) => void
  onPickMaterials: () => void
}) {
  const fields = schema?.fields ?? {}
  const meshFields = schema?.mesh_fields ?? {}
  const behaviors = choicesOf(fields.behavior)
  const representations = choicesOf(fields.representation)
  const methods = choicesOf(meshFields.method)
  const orders = choicesOf(meshFields.order)
  const names = bodies.map((one) => one.name)
  const rows = names.map((name) => settingOf(settings, name))
  const materialChoices: Choice[] = [
    { value: '', label: '미지정' },
    ...materials.map((one, index) => ({ value: String(index), label: nameOf(one) })),
  ]

  /** 이 파트의 물성 자리 — 둘 이상이면 「중복」(저장이 막힌다). */
  function materialValue(name: string): string {
    const on = materialsOn(materials, name)
    return on.length === 0 ? '' : on.length === 1 ? String(on[0]) : MIXED
  }

  function assign(targets: string[], value: string) {
    if (value === MIXED) return
    let next = materials
    for (const name of targets) next = assignBody(next, names, name, value === '' ? null : Number(value))
    onMaterialsChange(next)
  }

  function change(targets: string[], patch: Parameters<typeof withSetting>[2]) {
    let next = settings
    for (const name of targets) next = withSetting(next, name, patch)
    onSettingsChange(next)
  }

  const single = names.length === 1 && names[0] === ALL_BODIES
  /**
   * 형상에 없는 파트의 줄 — 파트 이름이 바뀌었거나 MCP 가 적은 것. 표에 안 보이면 지울 길이 없고,
   * 그 줄 때문에 저장이 막힌다. 따로 보여 주고 지우게 한다.
   */
  const orphans = settings.filter((one) => !names.includes(one.name))
  const anyShell = rows.some((one) => one.representation === 'shell' && !one.suppressed)
  const anyOff = rows.some((one) => one.suppressed)
  const title = (field: FieldSchema | undefined, fallback: string) => field?.title ?? fallback

  /** 한 줄의 칸들 — 파트 하나이거나 「모든 파트」(`targets` 가 여럿, 값이 갈리면 혼합). */
  function cells(label: string, targets: string[], all: boolean) {
    const of = targets.map((name) => settingOf(settings, name))
    const value = (pick: (one: (typeof of)[number]) => string) => common(of.map(pick))
    const off = !all && of[0].suppressed
    const rigid = !all && of[0].behavior === 'rigid'
    const size = value((one) => (one.mesh.element_size === null ? '' : String(one.mesh.element_size)))
    const offValue = value((one) => String(one.suppressed))
    return (
      <>
        <TableCell>
          <Select
            label={`${label} 물성`}
            value={common(targets.map(materialValue))}
            choices={materialChoices}
            mixedLabel={all ? '혼합' : '물성 중복'}
            disabled={off || materials.length === 0}
            onChange={(next) => assign(targets, next)}
          />
        </TableCell>
        <TableCell>
          <Select
            label={`${label} ${title(fields.behavior, '거동')}`}
            value={value((one) => one.behavior)}
            choices={behaviors}
            mixedLabel={all ? '혼합' : undefined}
            disabled={off}
            onChange={(next) => next !== MIXED && change(targets, { behavior: next as 'deformable' | 'rigid' })}
          />
        </TableCell>
        <TableCell>
          <Select
            label={`${label} ${title(fields.representation, '표현')}`}
            value={value((one) => one.representation)}
            choices={representations}
            mixedLabel={all ? '혼합' : undefined}
            disabled={off || rigid}
            onChange={(next) => next !== MIXED && change(targets, { representation: next as 'solid' | 'shell' })}
          />
        </TableCell>
        <TableCell className="text-center">
          <input
            type="checkbox"
            aria-label={`${label} ${title(fields.suppressed, '해석 제외')}`}
            checked={offValue === 'true'}
            ref={(box) => {
              if (box) box.indeterminate = offValue === MIXED
            }}
            onChange={(e) => change(targets, { suppressed: e.target.checked })}
          />
        </TableCell>
        <TableCell>
          <NumberText
            aria-label={`${label} ${title(meshFields.element_size, '요소 크기')}`}
            className="h-8 w-24 text-xs"
            value={size === MIXED ? '' : size}
            placeholder={size === MIXED ? '혼합' : '자동'}
            disabled={off}
            onText={(text) => change(targets, { mesh: { element_size: sizeOf(text) } })}
          />
        </TableCell>
        <TableCell>
          <Select
            label={`${label} ${title(meshFields.method, '요소 형상')}`}
            value={value((one) => one.mesh.method)}
            choices={methods}
            mixedLabel={all ? '혼합' : undefined}
            disabled={off}
            onChange={(next) => next !== MIXED && change(targets, { mesh: { method: next } })}
          />
        </TableCell>
        <TableCell>
          <Select
            label={`${label} ${title(meshFields.order, '요소 차수')}`}
            value={value((one) => one.mesh.order)}
            choices={orders}
            mixedLabel={all ? '혼합' : undefined}
            disabled={off}
            onChange={(next) => next !== MIXED && change(targets, { mesh: { order: next } })}
          />
        </TableCell>
      </>
    )
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-6xl">
        <DialogHeader>
          <DialogTitle>{schema?.label ?? '파트별 설정'}</DialogTitle>
          <DialogDescription>{schema?.intro}</DialogDescription>
        </DialogHeader>
        <div className="max-h-[60vh] overflow-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>파트</TableHead>
                <TableHead className="min-w-36">물성</TableHead>
                <TableHead className="min-w-24">{title(fields.behavior, '거동')}</TableHead>
                <TableHead className="min-w-24">{title(fields.representation, '표현')}</TableHead>
                <TableHead className="text-center">{title(fields.suppressed, '해석 제외')}</TableHead>
                <TableHead>
                  {title(meshFields.element_size, '요소 크기')} ({lengthUnit})
                </TableHead>
                <TableHead className="min-w-32">{title(meshFields.method, '요소 형상')}</TableHead>
                <TableHead className="min-w-28">{title(meshFields.order, '요소 차수')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {names.length > 1 && (
                <TableRow className="bg-muted/40 hover:bg-muted/40">
                  <TableCell className="text-xs font-medium">모든 파트</TableCell>
                  {cells('모든 파트', names, true)}
                </TableRow>
              )}
              {bodies.map((body) => (
                <TableRow key={body.name} className={settingOf(settings, body.name).suppressed ? 'opacity-60' : undefined}>
                  <TableCell>
                    <p className="text-sm font-medium">{single ? '전체 (단일 파트)' : body.name}</p>
                    {body.volume !== undefined && (
                      <p className="text-muted-foreground text-[11px]">부피 {Math.round(body.volume).toLocaleString()} mm³</p>
                    )}
                  </TableCell>
                  {cells(body.name, [body.name], false)}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
        {orphans.length > 0 && (
          <div role="note" className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs">
            <p>형상에 없는 파트의 설정이 있습니다. 이 설정이 있으면 저장할 수 없습니다.</p>
            <ul className="mt-1 space-y-0.5">
              {orphans.map((one) => (
                <li key={one.name} className="flex items-center gap-2">
                  <span className="font-medium">‘{one.name}’</span>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-6 text-xs"
                    onClick={() => onSettingsChange(settings.filter((other) => other.name !== one.name))}
                  >
                    삭제
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        )}
        <ul className="text-muted-foreground space-y-0.5 text-xs">
          {materials.length === 0 && (
            <li>
              추가된 물성이 없습니다.{' '}
              <button type="button" className="underline" onClick={onPickMaterials}>
                물성 선택
              </button>
            </li>
          )}
          <li>요소 크기를 비워 두면 국부 메시 ‘전체’ 또는 해석 플랫폼의 기본값을 따릅니다. 수 또는 =식으로 입력합니다. 구멍면처럼 일부 면만 촘촘하게 하려면 ‘국부 메시’를 사용하십시오.</li>
          {anyShell && <li>쉘 파트가 있으면 DOE가 설계점마다 중간면 STEP을 함께 생성합니다. 두께가 일정한 판만 중간면을 만들 수 있습니다.</li>}
          {anyOff && <li>해석에서 제외한 파트에 걸린 구속, 하중, 접촉, 초기조건이 있으면 저장할 수 없습니다.</li>}
        </ul>
        <DialogFooter>
          <Button onClick={onClose}>닫기</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
