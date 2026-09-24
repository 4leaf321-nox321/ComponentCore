/**
 * 해석 조건의 창들 — **3D 를 가리지 않는다.**
 *
 * 조건은 적용 대상(면 · 엣지 · 바디)을 3D 에서 지정해야 한다. 막이 뒤를 덮는 모달이면 그
 * 지정을 할 수 없어 창을 닫고 3D 를 누르고 다시 열기를 되풀이한다. 도면 편집기의 측정 창과
 * 같이 **막 없이 · 끌어서 옮기며 · 띄운 채로 3D 를 누른다**(`MeasureDialog`).
 */

import type { SelectorCandidate } from '@/modules/conditions/api'
import type { MeasurePick } from '@/shared/viewer/PickViewer'
import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'

/** 3D 오른쪽에 붙여 세우는 창. 가운데면 지정하려는 자리를 가린다 — 끌어서 옮길 수 있다. */
export function FloatingWindow({
  open,
  title,
  description,
  onClose,
  children,
  footer,
  className = 'top-24',
}: {
  open: boolean
  title: string
  description?: React.ReactNode
  onClose: () => void
  children: React.ReactNode
  footer?: React.ReactNode
  /** 세로 자리 — 두 창이 함께 뜨는 드문 경우 겹치지 않게 비켜 세운다. */
  className?: string
}) {
  return (
    <Dialog open={open} modal={false} onOpenChange={(value) => !value && onClose()}>
      <DialogContent
        overlay={false}
        className={`${className} right-6 left-auto max-h-[75vh] w-96 translate-x-0 translate-y-0 sm:max-w-md`}
        // 3D 를 눌러도 닫히지 않는다 — 창을 띄운 채 형상을 지정하는 것이 이 창의 쓰임이다.
        onInteractOutside={(event) => event.preventDefault()}
        onOpenAutoFocus={(event) => event.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle className="text-base">{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        <div className="space-y-3">{children}</div>
        {footer && <DialogFooter>{footer}</DialogFooter>}
      </DialogContent>
    </Dialog>
  )
}

/** 3D 에서 고른 것 하나 — 그 자리를 부를 **규칙 후보들**과 지금 고른 후보. */
export interface Member {
  /** 같은 것을 다시 눌렀는지 가르는 열쇠(면 · 엣지 번호, 점 좌표, 바디 이름). */
  key: string
  /** 사람이 읽을 종류 — 면 · 엣지 · 점 · 바디. */
  label: string
  /** 선택 그룹의 종류(`face` · `edge` · `vertex` · `body`) — **한 그룹은 한 종류**다. */
  entity: string
  /** 3D 에서 누른 그것 — 담은 것을 3D 에 번호와 함께 표시한다. */
  pick: MeasurePick
  candidates: SelectorCandidate[]
  chosen: number
}

/**
 * 선택 그룹에 담긴 것들 — 고른 것마다 **무엇으로 부를지**(규칙)를 고른다.
 *
 * 좌표가 아니라 규칙으로 저장한다(「아래쪽 면」 · 「반지름 4.25 원통면」) — 치수가 바뀌어도
 * 같은 것을 가리키게. 규칙이 지금 몇 개에 맞는지 함께 보인다: 구멍 하나를 골랐어도 「같은
 * 반지름 원통면(4 개)」 을 고르면 넷이 한꺼번에 들어간다. 기본은 **고른 그것 하나**다 —
 * 하나씩 골라 묶는 중이므로.
 */
export function SelectionMembers({
  members,
  onChoose,
  onRemove,
  onClear,
  name,
  onName,
  placeholder,
  existing,
  actions,
}: {
  members: Member[]
  onChoose: (index: number, candidate: number) => void
  onRemove: (index: number) => void
  onClear: () => void
  name: string
  onName: (next: string) => void
  placeholder: string
  /** 같은 규칙의 선택 그룹이 이미 있으면 그 이름 — 새로 만들지 않고 그것을 쓴다. */
  existing: string | null
  actions?: React.ReactNode
}) {
  return (
    <div className="bg-muted/40 space-y-2 rounded-md border p-2">
      <div className="flex items-center justify-between">
        <p className="font-medium">
          선택 {members.length} {members[0] && <span className="text-muted-foreground text-xs">({members[0].label})</span>}
        </p>
        <Button size="sm" variant="ghost" className="h-6 px-2 text-xs" onClick={onClear} disabled={members.length === 0}>
          비우기
        </Button>
      </div>
      {members.length === 0 ? (
        <p className="text-muted-foreground rounded-md border border-dashed p-2 text-xs">
          3D 에서 형상을 선택합니다. Ctrl 또는 Shift 를 누른 채 선택하면 더해지고, Shift 를 누른 채 끌면 사각형
          안의 것이 더해집니다.
        </p>
      ) : (
        <ol className="space-y-1">
          {members.map((member, index) => (
            <li key={member.key} className="flex items-center gap-1">
              <span className="text-muted-foreground w-5 shrink-0 text-center font-mono text-xs">{index + 1}</span>
              <select
                aria-label={`${index + 1}번 선택 규칙`}
                className="bg-background min-w-0 flex-1 rounded border px-1 py-0.5 text-xs"
                value={member.chosen}
                onChange={(e) => onChoose(index, Number(e.target.value))}
              >
                {member.candidates.map((one, at) => (
                  <option key={one.label} value={at}>
                    {one.label} (현재 {one.matches} 개){one.stable === false ? ' — 치수 변경에 취약' : ''}
                  </option>
                ))}
              </select>
              <button
                type="button"
                aria-label={`${index + 1}번 제외`}
                className="text-muted-foreground hover:text-destructive rounded px-1"
                onClick={() => onRemove(index)}
              >
                ×
              </button>
            </li>
          ))}
        </ol>
      )}
      {/*
        **좌표만 쓰는 규칙은 말없이 헛집는다** — DOE 가 치수를 바꾸면 못 찾는 게 아니라 가장
        가까운 딴 형상을 집는다. 고른 사람이 알고 고르게 한다.
      */}
      {members.some((one) => one.candidates[one.chosen]?.stable === false) && (
        <p className="rounded border border-amber-300 bg-amber-50 p-1 text-xs text-amber-800 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
          ⚠ 좌표 기준 규칙이 있습니다 — DOE 로 치수가 바뀌면 다른 형상을 선택할 수 있습니다. 방향으로 거른 규칙(「… 중 이
          면」)을 권장합니다.
        </p>
      )}
      <p className="text-muted-foreground text-[11px]">
        좌표가 아니라 <strong>선택 규칙</strong>으로 저장합니다 — 치수가 변경되어도 같은 형상을 가리킵니다. Ctrl 로 다시
        누르면 제외됩니다.
      </p>
      {existing ? (
        // 같은 자리를 두 번 선택해도 그룹이 둘이 되지 않는다 — 조건마다 같은 면을 가리키는 일이 흔하다.
        <p className="text-muted-foreground text-xs">
          같은 선택 규칙의 선택 그룹 「{existing}」 이(가) 이미 있습니다 — 그 그룹을 사용합니다.
        </p>
      ) : (
        members.length > 0 && (
          <div className="space-y-1">
            <Label htmlFor="group-name">그룹 이름</Label>
            <Input id="group-name" value={name} placeholder={placeholder} onChange={(e) => onName(e.target.value)} />
          </div>
        )
      )}
      {actions && <div className="flex gap-2">{actions}</div>}
    </div>
  )
}
