/**
 * 상태 배지 — **말과 색을 한 곳에서 정한다.**
 *
 * 화면마다 제 색을 고르면 같은 "실패" 가 목록에서는 회색이고 상세에서는 빨강이 된다.
 */

import { cn } from '@/shared/lib/utils'

type Tone = 'neutral' | 'info' | 'accent' | 'good' | 'warn' | 'bad'

const TONE_CLASS: Record<Tone, string> = {
  neutral: 'bg-muted text-muted-foreground',
  info: 'bg-sky-500/10 text-sky-700 dark:text-sky-400',
  accent: 'bg-violet-500/10 text-violet-700 dark:text-violet-400',
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
  running: { label: '실행 중', tone: 'warn' },
  done: { label: '완료', tone: 'good' },
  failed: { label: '실패', tone: 'bad' },
  cancelled: { label: '취소됨', tone: 'neutral' },
  cancelling: { label: '취소 중', tone: 'warn' },
}

const INTERFERENCE: Record<string, { label: string; tone: Tone }> = {
  ok: { label: '간섭 없음', tone: 'good' },
  bad: { label: '간섭 있음', tone: 'bad' },
}

/** VOC 의 절차 — 서버 `voc.models.VOC_STATUS_LABELS` 와 같은 말. 지나온 곳(종료)은 흐리게. */
const VOC: Record<string, { label: string; tone: Tone }> = {
  open: { label: '등록', tone: 'info' },
  accepted: { label: '접수', tone: 'accent' },
  in_progress: { label: '처리 중', tone: 'warn' },
  resolved: { label: '해결', tone: 'good' },
  closed: { label: '종료', tone: 'neutral' },
  rejected: { label: '반려', tone: 'bad' },
}

const TABLES = { account: ACCOUNT, run: RUN, interference: INTERFERENCE, voc: VOC } as const

/** 배지 없이 말만 — 필터 칩 · 확인 창처럼 배지를 그리지 않는 자리. */
export function statusLabel(kind: keyof typeof TABLES, value: string): string {
  return TABLES[kind][value]?.label ?? value
}

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
