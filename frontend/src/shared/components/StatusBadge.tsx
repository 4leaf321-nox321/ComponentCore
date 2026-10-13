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

// --- StandardPlatform 에서 들인 표(ADR 0008) ---------------------------------------------------

const NOTICE: Record<string, { label: string; tone: Tone }> = {
  info: { label: '안내', tone: 'neutral' },
  warning: { label: '주의', tone: 'warn' },
  urgent: { label: '긴급', tone: 'bad' },
}

const WORKSPACE: Record<string, { label: string; tone: Tone }> = {
  // **보관은 나쁨이 아니라 중립이다** — 사고가 아니라 조직의 생애다.
  active: { label: '사용', tone: 'good' },
  archived: { label: '보관', tone: 'neutral' },
}

const OBJECT: Record<string, { label: string; tone: Tone }> = {
  active: { label: '사용', tone: 'good' },
  // **더 이상 쓰지 않음은 나쁨이 아니다.** picker 에서 숨을 뿐, 이미 걸린 값과
  // 관계는 그대로 남는다 — 지운 것이 아니다.
  deprecated: { label: '안 씀', tone: 'neutral' },
}

const TOKEN: Record<string, { label: string; tone: Tone }> = {
  active: { label: '사용', tone: 'good' },
  // **만료는 주의다** — 그 토큰을 아직 넣어 둔 연동이 있으면 지금 인증에 실패하고 있다.
  expired: { label: '만료', tone: 'warn' },
  // 폐기는 사고가 아니라 끝낸 일이다.
  revoked: { label: '폐기', tone: 'neutral' },
}

/** 느린 요청 · 큰 응답(ADR 0026) — 경로 틀 한 줄의 표시. */
const PERFORMANCE: Record<string, { label: string; tone: Tone }> = {
  // **느린 것은 고장이 아니라 주의다** — 빨강은 멎은 것(실패 · 오류)의 색이다.
  slow: { label: '느림', tone: 'warn' },
  large: { label: '큼', tone: 'warn' },
  // 파일 응답은 크고 받는 쪽 속도를 타는 것이 정상이다 — 문턱 판정에서 뺀다는 표시.
  file: { label: '파일', tone: 'neutral' },
}

const TABLES = {
  account: ACCOUNT,
  run: RUN,
  interference: INTERFERENCE,
  voc: VOC,
  object: OBJECT,
  notice: NOTICE,
  performance: PERFORMANCE,
  token: TOKEN,
  workspace: WORKSPACE,
} as const

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
