/**
 * 상단 바 — 사이드바 토글 · 객체 검색 · 부서 선택 · 알림 · 테마 · 계정 메뉴.
 *
 * 검색 · 부서 선택 · 알림은 StandardPlatform 의 것을 들였다(ADR 0008). **검색 칸은 결과를 그리지
 * 않는다** — 친 말을 `/search?q=` 로 넘길 뿐이다(주소로 공유되고 뒤로가기가 산다). 찾는 대상은
 * 온톨로지 객체다 — 작업 · 부품 · 지그는 각 목록 화면에서 찾는다.
 *
 * 부서 선택기는 **내가 속한 부서만** 보이고, 소속이 없으면 아예 안 그린다 — 부서는 온톨로지
 * 객체에만 쓰여서, 형상 작업만 하는 사람에게 「소속된 부서가 없습니다」 는 할 일이 아니다.
 */

import { useState } from 'react'
import { KeyRound, LogOut, Moon, PanelLeft, Search, Sun, User, UserCog } from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'

import { useAuth } from '@/shared/auth/AuthContext'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/shared/components/ui/dropdown-menu'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/components/ui/select'
import { ChangePasswordDialog } from '@/shared/layout/ChangePasswordDialog'
import { NotificationBell } from '@/shared/layout/NotificationBell'
import { useTheme } from '@/shared/theme/ThemeProvider'

interface HeaderProps {
  onToggleSidebar: () => void
  workspaceSlug?: string | null
}

export function Header({ onToggleSidebar, workspaceSlug = null }: HeaderProps) {
  const { theme, toggle } = useTheme()
  const { user, logout } = useAuth()
  const [changingPassword, setChangingPassword] = useState(false)
  const [query, setQuery] = useState('')
  const navigate = useNavigate()
  const params = useParams<{ slug?: string }>()

  const memberships = user?.memberships ?? []
  const current = memberships.find((one) => one.slug === workspaceSlug)

  function switchTo(slug: string) {
    // 부서 스코프 화면에 있으면 같은 화면의 다른 부서로, 아니면 그 부서 홈으로.
    const suffix = params.slug ? window.location.pathname.split(`/w/${params.slug}`)[1] : ''
    navigate(`/w/${slug}${suffix ?? ''}`)
  }

  async function signOut() {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <header className="bg-background flex h-14 shrink-0 items-center gap-2 border-b px-3">
      <Button variant="ghost" size="icon" onClick={onToggleSidebar} aria-label="사이드바 접기/확장">
        <PanelLeft className="size-4" />
      </Button>

      <form
        className="relative ml-1 w-40 sm:w-64"
        onSubmit={(event) => {
          event.preventDefault()
          const word = query.trim()
          if (!word) return
          navigate(`/search?q=${encodeURIComponent(word)}`)
          setQuery('')
        }}
      >
        <Search className="text-muted-foreground absolute top-1/2 left-2 size-4 -translate-y-1/2" />
        <Input
          className="h-8 pl-8"
          value={query}
          placeholder="객체 검색"
          aria-label="기준정보 객체에서 검색"
          onChange={(event) => setQuery(event.target.value)}
        />
      </form>

      {/* **경로가 보이는 선택기.** 같은 이름의 팀이 둘일 수 있어 이름만으로는 어느 부서인지 모른다. */}
      {memberships.length > 0 && (
        <Select value={workspaceSlug ?? undefined} onValueChange={switchTo}>
          <SelectTrigger className="h-8 max-w-64 border-0 shadow-none" aria-label="부서 선택">
            <SelectValue placeholder="부서" />
          </SelectTrigger>
          <SelectContent>
            {memberships.map((one) => (
              <SelectItem key={one.slug} value={one.slug}>
                {one.path}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
      {current?.role === 'manager' && (
        <span className="text-muted-foreground hidden text-xs sm:inline">부서 관리자</span>
      )}

      <div className="flex-1" />

      <NotificationBell />

      <Button variant="ghost" size="icon" onClick={toggle} aria-label="테마 전환">
        {theme === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
      </Button>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="sm">
            <User className="size-4" />
            {user?.display_name ?? '계정'}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuLabel className="font-normal">
            <p className="text-sm font-medium">{user?.display_name}</p>
            <p className="text-muted-foreground truncate text-xs">{user?.email}</p>
            {user?.is_system_admin && (
              <p className="text-muted-foreground mt-1 text-xs">시스템 관리자</p>
            )}
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => navigate('/me')}>
            <UserCog className="size-4" />내 정보
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setChangingPassword(true)}>
            <KeyRound className="size-4" />
            비밀번호 변경
          </DropdownMenuItem>
          <DropdownMenuItem onClick={signOut}>
            <LogOut className="size-4" />
            로그아웃
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <ChangePasswordDialog
        open={changingPassword}
        onClose={() => setChangingPassword(false)}
        onChanged={async () => {
          setChangingPassword(false)
          await logout()
        }}
      />
    </header>
  )
}
