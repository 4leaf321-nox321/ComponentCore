/**
 * 상태 배지 — **말과 색을 한 곳에서 정한다.**
 *
 * 화면마다 제 색을 고르면 같은 "실패" 가 목록에서는 회색이고 상세에서는 빨강이 된다.
 */

import { cn } from '@/shared/lib/utils'

type Tone = 'neutral' | 'good' | 'warn' | 'bad'

const TONE_CLASS: Record<Tone, string> = {
  neutral: 'bg-muted text-muted-foreground',
  good: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
  warn: 'bg-amber-500/10 text-amber-700 dark:text-amber-400',
  bad: 'bg-destructive/10 text-destructive',
}

const ACCOUNT: Record<string, { label: string; tone: Tone }> = {
  active: { label: '정상', tone: 'good' },
  suspended: { label: '정지', tone: 'bad' },
}

const RUN: Record<string, { label: string; tone: Tone }> = {
  queued: { label: '대기', tone: 'neutral' },
  running: { label: '생성 중', tone: 'warn' },
  done: { label: '완료', tone: 'good' },
  failed: { label: '실패', tone: 'bad' },
}

const INTERFERENCE: Record<string, { label: string; tone: Tone }> = {
  ok: { label: '간섭 없음', tone: 'good' },
  bad: { label: '간섭 있음', tone: 'bad' },
}

const TABLES = { account: ACCOUNT, run: RUN, interference: INTERFERENCE } as const

export function StatusBadge({
  kind,
  value,
  className,
}: {
  kind: keyof typeof TABLES
  value: string
  className?: string
}) {
  const entry = TABLES[kind][value] ?? { label: value, tone: 'neutral' as Tone }
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium',
        TONE_CLASS[entry.tone],
        className,
      )}
    >
      {entry.label}
    </span>
  )
}
