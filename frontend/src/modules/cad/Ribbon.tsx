/**
 * 리본 — 탭마다 아이콘 단추. 「+ 피처」 드롭다운 하나에 스물을 넣으면 매번 찾고, 가로 한 줄에
 * 다 늘어놓으면 곧 화면이 찬다. 탭이 종류를 가르고 단추는 **누르는 것처럼** 보여야 한다.
 */

import type { LucideIcon } from 'lucide-react'

import { cn } from '@/shared/lib/utils'

export function RibbonButton({
  icon: Icon,
  label,
  onClick,
  active,
  disabled,
  title,
}: {
  icon: LucideIcon
  label: string
  onClick: () => void
  active?: boolean
  disabled?: boolean
  title?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title ?? label}
      className={cn(
        'flex h-14 w-[4.25rem] shrink-0 flex-col items-center justify-center gap-1 rounded-md border text-[11px] leading-none shadow-sm transition-colors',
        'bg-card hover:bg-accent hover:border-foreground/30 active:translate-y-px active:shadow-none',
        active && 'bg-primary text-primary-foreground border-primary hover:bg-primary/90',
        disabled && 'cursor-not-allowed opacity-40 hover:bg-card hover:border-border active:translate-y-0',
      )}
    >
      <Icon className="size-5" />
      <span className="truncate px-1">{label}</span>
    </button>
  )
}

export function RibbonGroup({ title, children }: { title?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-end gap-1 border-r pr-2 last:border-r-0">
      <div className="flex flex-col gap-1">
        <div className="flex gap-1">{children}</div>
        {title && <span className="text-muted-foreground text-center text-[10px]">{title}</span>}
      </div>
    </div>
  )
}
