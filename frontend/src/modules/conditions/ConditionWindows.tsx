/**
 * 해석 조건의 창들 — **3D 를 가리지 않는다.**
 *
 * 조건은 적용 대상(면 · 엣지 · 바디)을 3D 에서 지정해야 한다. 막이 뒤를 덮는 모달이면 그
 * 지정을 할 수 없어 창을 닫고 3D 를 누르고 다시 열기를 되풀이한다. 도면 편집기의 측정 창과
 * 같이 **막 없이 · 끌어서 옮기며 · 띄운 채로 3D 를 누른다**(`MeasureDialog`).
 */

import type { SelectorCandidate } from '@/modules/conditions/api'
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

export interface Candidates {
  what: string
  /** 사람이 읽을 종류 — 면 · 엣지 · 점 · 바디. */
  label: string
  list: SelectorCandidate[]
}

/**
 * 3D 에서 선택한 자리를 **무엇으로 부를지** 고른다 — 좌표가 아니라 선택 규칙으로.
 *
 * 서버가 후보를 여럿 준다(「아래쪽 면」 · 「반지름 4.25 원통면」). 하나를 자동으로 정하면
 * 「볼트 구멍 넷」 을 원했는데 「이 구멍 하나」 가 저장되는 날이 온다 — 그래서 **지금 몇 개에
 * 맞는지**를 함께 보여 사람이 고른다.
 */
export function CandidatePicker({
  candidates,
  picked,
  onPicked,
  name,
  onName,
  existing,
  confirmLabel,
  onConfirm,
  onCancel,
}: {
  candidates: Candidates
  picked: number
  onPicked: (index: number) => void
  name: string
  onName: (next: string) => void
  /** 고른 규칙과 **같은 이름표가 이미 있으면** 그 이름 — 새로 만들지 않고 그것을 쓴다. */
  existing: string | null
  confirmLabel: string
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <div className="bg-muted/40 space-y-2 rounded-md border p-2">
      <p className="font-medium">{candidates.label} 선택됨</p>
      <p className="text-muted-foreground text-xs">
        좌표가 아니라 <strong>선택 규칙</strong>으로 저장합니다 — 치수가 변경되어도 같은 형상을 가리킵니다.
      </p>
      <ul className="space-y-1">
        {candidates.list.map((one, index) => (
          <li key={one.label}>
            <button
              type="button"
              aria-pressed={picked === index}
              className={`bg-background w-full rounded border px-2 py-1 text-left ${picked === index ? 'border-primary' : ''}`}
              onClick={() => onPicked(index)}
            >
              {one.label}
              <span className="text-muted-foreground ml-2 text-xs">현재 {one.matches} 개</span>
            </button>
          </li>
        ))}
      </ul>
      {existing ? (
        // 같은 자리를 두 번 선택해도 이름표가 둘이 되지 않는다 — 조건마다 같은 면을 가리키는 일이 흔하다.
        <p className="text-muted-foreground text-xs">
          같은 선택 규칙의 이름표 「{existing}」 이(가) 이미 있습니다 — 그 이름표를 사용합니다.
        </p>
      ) : (
        <div className="space-y-1">
          <Label htmlFor="ns-name">이름표 이름</Label>
          <Input
            id="ns-name"
            value={name}
            placeholder={candidates.list[picked]?.label ?? ''}
            onChange={(e) => onName(e.target.value)}
          />
        </div>
      )}
      <div className="flex gap-2">
        <Button size="sm" onClick={onConfirm}>
          {confirmLabel}
        </Button>
        <Button size="sm" variant="ghost" onClick={onCancel}>
          취소
        </Button>
      </div>
    </div>
  )
}
