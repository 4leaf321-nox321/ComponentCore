/**
 * 규격 부품표 — 한 줄로 보이고 **CSV 로 받는다.** 구매 · 조립이 그대로 쓰는 것은 화면의 글자가
 * 아니라 표다(품번 · 이름 · 종류 · 수량). 클램프 고정 볼트(`screw`)도 한 줄이다.
 *
 * 엑셀이 한글을 깨지 않게 UTF-8 BOM 을 앞에 두고, 줄은 CRLF 로 끊는다.
 */

import { Download } from 'lucide-react'

import { bomLine } from '@/modules/jigs/featureLabels'
import { Button } from '@/shared/components/ui/button'
import { cn } from '@/shared/lib/utils'

export interface BomRow {
  part_no: string
  name: string
  kind: string
  count: number
}

/** 종류의 이름 — 서버 `core/standard.KINDS` 와 클램프 고정 볼트. */
const KIND_LABELS: Record<string, string> = { support: '받침', pin: '위치 핀', clamp: '토글 클램프', screw: '볼트' }

function cell(value: string | number): string {
  const text = String(value)
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
}

export function bomCsv(rows: BomRow[]): string {
  const lines = [['품번', '이름', '종류', '수량'], ...rows.map((one) => [one.part_no, one.name, KIND_LABELS[one.kind] ?? one.kind, one.count])]
  return `﻿${lines.map((line) => line.map(cell).join(',')).join('\r\n')}\r\n`
}

/** 파일 이름에 못 쓰는 글자를 뺀다 — `지그 1/2` 가 폴더로 읽히지 않게. */
function safeName(name: string): string {
  return name.replace(/[\\/:*?"<>|]+/g, ' ').trim() || '지그'
}

export function saveBomCsv(rows: BomRow[], name: string): void {
  const href = URL.createObjectURL(new Blob([bomCsv(rows)], { type: 'text/csv;charset=utf-8' }))
  const anchor = document.createElement('a')
  anchor.href = href
  anchor.download = `${safeName(name)}-부품표.csv`
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(href), 10_000)
}

/** 「규격 부품: SUP-16 받침 × 4 · …」 와 CSV 다운로드. 부품표가 비면 아무것도 그리지 않는다. */
export function BomLine({ rows, name, className }: { rows: BomRow[] | undefined; name: string; className?: string }) {
  if (!rows || rows.length === 0) return null
  return (
    <div className={cn('flex flex-wrap items-center gap-2', className)}>
      <p>규격 부품: {bomLine(rows)}</p>
      <Button type="button" size="sm" variant="outline" className="h-6 px-2 text-xs" onClick={() => saveBomCsv(rows, name)}>
        <Download className="size-3" />
        부품표 CSV
      </Button>
    </div>
  )
}
