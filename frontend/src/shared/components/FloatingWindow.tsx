/**
 * **3D 를 가리지 않는 창** — 막 없이 · 끌어서 옮기며 · 띄운 채로 3D 를 누른다. 도면 편집기의
 * 측정 · 좌표계, 해석 조건의 조건 · 선택 그룹 창이 쓴다.
 */

import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/components/ui/dialog'

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
