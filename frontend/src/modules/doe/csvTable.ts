/**
 * 설계점 표(CSV) 읽고 쓰기 — 「표 직접 넣기」 가 쓴다.
 *
 * 엑셀에서 복사한 것(탭)과 CSV 파일(쉼표 · 세미콜론)을 다 받는다. 첫 줄이 변수 이름이고, 번호 열
 * (`point` · `번호` · `#`)은 버린다 — 설계점 번호는 줄 순서가 정한다. 값은 글자 그대로 보내고
 * 수로 읽는 것은 서버가 한다(어느 줄 · 어느 칸이 틀렸는지 서버가 짚는다).
 */

export interface ParsedTable {
  columns: string[]
  rows: Record<string, string>[]
  /** 읽다가 버린 것 — 빈 이름의 열, 칸 수가 다른 줄. */
  problems: string[]
}

/** 번호 열 — 줄 순서가 번호라 버린다. */
const INDEX_COLUMNS = new Set(['point', '번호', '#', 'no', 'No'])

function delimiterOf(header: string): string {
  if (header.includes('\t')) return '\t'
  if (header.includes(';') && !header.includes(',')) return ';'
  return ','
}

/** 따옴표로 묶인 칸까지 — 엑셀이 쉼표가 든 값을 그렇게 쓴다. */
function splitLine(line: string, delimiter: string): string[] {
  const out: string[] = []
  let cell = ''
  let quoted = false
  for (let i = 0; i < line.length; i += 1) {
    const char = line[i]
    if (quoted) {
      if (char === '"' && line[i + 1] === '"') {
        cell += '"'
        i += 1
      } else if (char === '"') quoted = false
      else cell += char
    } else if (char === '"') quoted = true
    else if (char === delimiter) {
      out.push(cell)
      cell = ''
    } else cell += char
  }
  out.push(cell)
  return out.map((one) => one.trim())
}

export function parseTable(text: string): ParsedTable {
  const lines = text
    .replace(/^﻿/, '')
    .split(/\r?\n/)
    .filter((one) => one.trim() !== '')
  if (lines.length === 0) return { columns: [], rows: [], problems: [] }
  const delimiter = delimiterOf(lines[0])
  const header = splitLine(lines[0], delimiter)
  const problems: string[] = []
  const keep = header.map((name) => name !== '' && !INDEX_COLUMNS.has(name))
  if (header.some((name) => name === '')) problems.push('이름 없는 열은 버렸습니다')
  const columns = header.filter((_, i) => keep[i])
  const rows: Record<string, string>[] = []
  lines.slice(1).forEach((line, index) => {
    const cells = splitLine(line, delimiter)
    if (cells.length !== header.length) {
      problems.push(`${index + 2} 번째 줄은 칸이 ${cells.length} 개라 버렸습니다(머리는 ${header.length} 개)`)
      return
    }
    const row: Record<string, string> = {}
    header.forEach((name, i) => {
      if (keep[i]) row[name] = cells[i]
    })
    rows.push(row)
  })
  return { columns, rows, problems }
}

/** 표 → CSV 글자 — 「설정 바꿔 다시 만들기」 가 지난 표를 칸에 되돌려 놓는다. */
export function formatTable(columns: string[], rows: Record<string, unknown>[]): string {
  const cell = (value: unknown) => {
    const text = value === null || value === undefined ? '' : String(value)
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
  }
  return [columns.map(cell).join(','), ...rows.map((row) => columns.map((name) => cell(row[name])).join(','))].join('\n')
}
