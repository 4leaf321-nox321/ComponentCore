/**
 * 태그 줄 — 작업 · 부품 · 지그에 붙은 **온톨로지 객체**(백엔드 `tagging`, ADR 0011).
 *
 * 칩은 그 객체로 간다(`/o/<타입>/<id>`) — 거기서 이 태그가 붙은 다른 것들이 보인다. 「일반 태그」 가
 * 아닌 것은 타입 이름을 곁에 적는다: 같은 「A」 라도 고객사 A 와 프로젝트 A 는 다르다.
 *
 * 붙이기는 **타입을 고르고**(기본 「일반 태그」) 이름을 친다. 그 타입에서 이름이 맞는 것을 많이 쓴
 * 순으로 보이고, 똑같은 이름이 없으면 「늘리기」 타입에서는 새로 만든다 — 태그를 달수록 어휘가
 * 쌓인다. 「고르기」 타입은 있는 것에서만 고른다(새 이름은 관리자가 그 타입에 만든다).
 */

import { useEffect, useRef, useState } from 'react'
import { Plus, X } from 'lucide-react'
import { Link } from 'react-router-dom'

import { DEFAULT_TAG_TYPE, tagsApi } from '@/modules/tagging/api'
import type { AddTag, TagCandidate, TagItem, TagTarget } from '@/modules/tagging/api'
import { Button } from '@/shared/components/ui/button'
import { useResource } from '@/shared/hooks/useResource'

interface Props {
  target: TagTarget
  id: string
  /** 이 행을 고칠 수 있나 — 화면이 이미 정한 것(주인 · 관리자). 서버가 다시 본다. */
  canEdit: boolean
  /** 붙이거나 뗀 뒤 — 거르개 목록을 새로 읽을 화면이 쓴다. */
  onChanged?: (tags: TagItem[]) => void
}

export function TagField({ target, id, canEdit, onChanged }: Props) {
  const loaded = useResource(() => tagsApi.of(target, id), [target, id])
  // 고친 뒤 서버가 붙은 태그 전부를 돌려준다 — 그것을 그대로 쓴다(다시 묻지 않는다).
  const [fresh, setFresh] = useState<TagItem[] | null>(null)
  const [adding, setAdding] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const tags = fresh ?? (Array.isArray(loaded.data) ? loaded.data : [])

  async function act(run: () => Promise<TagItem[]>) {
    setBusy(true)
    setError(null)
    try {
      const next = await run()
      setFresh(next)
      onChanged?.(next)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '실패했습니다.')
    } finally {
      setBusy(false)
    }
  }

  // **곁 줄이 화면을 쓰러뜨리지 않게** — 못 읽으면 이 줄만 말한다.
  if (loaded.error && !fresh) return <span className="text-muted-foreground text-xs">태그를 불러오지 못했습니다.</span>

  return (
    <div className="flex flex-wrap items-center gap-1">
      {tags.map((one) => (
        <span key={one.object_id} className="bg-accent inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs">
          <Link to={`/o/${one.type_slug}/${one.object_id}`} className="hover:underline" title={`${one.type_label} — 온톨로지에서 보기`}>
            {one.label}
          </Link>
          {one.type_slug !== DEFAULT_TAG_TYPE && <span className="text-muted-foreground">· {one.type_label}</span>}
          {canEdit && (
            <button
              type="button"
              className="text-muted-foreground hover:text-destructive"
              onClick={() => void act(() => tagsApi.remove(target, id, one.object_id))}
              disabled={busy}
              aria-label={`${one.label} 태그 떼기`}
            >
              <X className="size-3" />
            </button>
          )}
        </span>
      ))}
      {tags.length === 0 && !canEdit && <span className="text-muted-foreground text-xs">—</span>}
      {canEdit && !adding && (
        <Button type="button" variant="ghost" size="sm" className="h-6 px-1.5 text-xs" onClick={() => setAdding(true)}>
          <Plus className="size-3" />
          태그
        </Button>
      )}
      {canEdit && adding && (
        <TagAdder
          taken={new Set(tags.map((one) => one.object_id))}
          busy={busy}
          onAdd={(body) => void act(() => tagsApi.add(target, id, body))}
          onClose={() => setAdding(false)}
        />
      )}
      {error && (
        <span role="alert" className="text-destructive text-xs">
          {error}
        </span>
      )}
    </div>
  )
}

/** 타입 하나를 고르고 그 안에서 찾는다 — 똑같은 이름이 없으면 (늘리기 타입이면) 새로 만든다. */
function TagAdder({
  taken,
  busy,
  onAdd,
  onClose,
}: {
  taken: Set<string>
  busy: boolean
  onAdd: (body: AddTag) => void
  onClose: () => void
}) {
  const types = useResource(() => tagsApi.types(), [])
  const kinds = Array.isArray(types.data) ? types.data : []
  const [slug, setSlug] = useState('')
  const kind = kinds.find((one) => one.slug === slug) ?? kinds[0]
  const [text, setText] = useState('')
  const [found, setFound] = useState<TagCandidate[]>([])
  const name = text.trim()

  // 치는 동안 묻지 않게 잠깐 기다렸다가 — 그 타입에서 이름에 든 것, 많이 쓴 것부터.
  useEffect(() => {
    if (!kind) return
    let alive = true
    const timer = setTimeout(() => {
      tagsApi
        .candidates(kind.slug, name, 8)
        .then((rows) => alive && setFound(Array.isArray(rows) ? rows : []))
        .catch(() => alive && setFound([]))
    }, 200)
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [kind, name])

  const exact = found.find((one) => one.label.toLowerCase() === name.toLowerCase())
  const options = found.filter((one) => !taken.has(one.object_id))

  const typed = useRef<HTMLInputElement>(null)

  // 붙인 뒤에는 이름 칸으로 돌아간다 — 이어서 치거나 Esc 로 닫는다. 후보 · 「새로 만들기」 를
  // 누르면 커서가 그 단추에 남아, 칸을 닫으려면 × 를 찾아 눌러야 했다(2026-10-24).
  function pick(body: AddTag) {
    if (busy) return
    onAdd(body)
    setText('')
    typed.current?.focus()
  }

  function submit() {
    if (!name || !kind) return
    // 똑같은 이름이 있으면 그것 — 없으면 서버가 별칭을 찾아 보고, 늘리기 타입이면 만든다.
    pick(exact ? { object_id: exact.object_id } : { type_slug: kind.slug, label: name })
  }

  return (
    // Esc 는 칸 어디서든 닫는다 — 타입 고르개 · 후보 단추에 있을 때도.
    <div
      className="relative"
      onKeyDown={(e) => {
        if (e.key === 'Escape') {
          e.preventDefault()
          onClose()
        }
      }}
    >
      <div className="flex items-center gap-1">
        <select
          aria-label="태그 타입"
          value={kind?.slug ?? ''}
          onChange={(e) => setSlug(e.target.value)}
          className="bg-background text-foreground h-6 rounded border px-1 text-xs"
          disabled={busy}
        >
          {kinds.map((one) => (
            <option key={one.slug} value={one.slug}>
              {one.label}
            </option>
          ))}
        </select>
        {/* 붙이는 동안에도 칸을 막지 않는다 — 막으면 커서가 빠져 Esc · 이어 치기가 안 된다. */}
        <input
          ref={typed}
          autoFocus
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              submit()
            }
          }}
          placeholder={kind?.can_create ? '이름 (Enter)' : '찾아서 고르기'}
          className="h-6 min-w-32 rounded border bg-transparent px-1 text-xs outline-none"
          aria-label="태그 이름"
          maxLength={80}
        />
        <button type="button" className="text-muted-foreground hover:text-foreground" onClick={onClose} aria-label="태그 붙이기 닫기">
          <X className="size-3" />
        </button>
      </div>
      {kind && (options.length > 0 || name) && (
        <ul aria-label="태그 후보" className="bg-popover text-popover-foreground absolute z-20 mt-1 w-64 rounded border p-1 shadow-md">
          {options.map((one) => (
            <li key={one.object_id}>
              <button
                type="button"
                className="hover:bg-accent flex w-full items-center justify-between rounded px-2 py-1 text-left text-xs"
                onClick={() => pick({ object_id: one.object_id })}
                disabled={busy}
              >
                <span>{one.label}</span>
                <span className="text-muted-foreground" title="붙은 곳">
                  {one.uses}
                </span>
              </button>
            </li>
          ))}
          {name && !exact && kind.can_create && (
            <li>
              <button
                type="button"
                className="hover:bg-accent w-full rounded px-2 py-1 text-left text-xs"
                onClick={submit}
                disabled={busy}
              >
                「{name}」 새로 만들기 <span className="text-muted-foreground">({kind.label})</span>
              </button>
            </li>
          )}
          {name && !exact && !kind.can_create && options.length === 0 && (
            <li className="text-muted-foreground px-2 py-1 text-xs">{kind.label}은(는) 있는 것에서만 고릅니다.</li>
          )}
        </ul>
      )}
    </div>
  )
}
