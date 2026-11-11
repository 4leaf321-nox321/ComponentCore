import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import AccountsAdminPage, { mailList } from '@/modules/accounts/AccountsAdminPage'
import type { Account } from '@/shared/api/types'

vi.mock('@/shared/auth/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'me', is_system_admin: true } }),
}))

const account = (id: string, email: string): Account => ({
  id,
  email,
  display_name: id,
  status: 'active',
  is_system_admin: false,
  must_change_password: false,
  created_at: '2026-01-01T00:00:00Z',
  deleted_at: null,
})

const ACCOUNTS = [account('kim', 'kim@example.local'), account('lee', 'lee@example.local'), account('root', 'admin')]

/** 운영 서버는 평문 HTTP 다 — `navigator.clipboard` 가 없고 execCommand 로만 복사된다. */
let copied: string[] = []
function plainHttp(accept = true) {
  Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true })
  Object.defineProperty(document, 'execCommand', {
    configurable: true,
    value: vi.fn(() => {
      copied.push((document.querySelector('textarea[readonly]') as HTMLTextAreaElement).value)
      return accept
    }),
  })
}

beforeEach(() => {
  copied = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(
    async () => new Response(JSON.stringify(ACCOUNTS), { status: 200, headers: { 'Content-Type': 'application/json' } }),
  )
})

const page = () =>
  render(
    <MemoryRouter>
      <AccountsAdminPage />
    </MemoryRouter>,
  )

test('받는 사람 칸에 붙일 목록 — 쌍반점으로 잇고, 메일 주소가 아닌 아이디는 빼고, 같은 주소는 한 번', () => {
  expect(mailList([...ACCOUNTS, account('kim2', 'KIM@example.local')])).toEqual({
    text: 'kim@example.local; lee@example.local',
    count: 2,
    skipped: ['admin'],
  })
})

test('HTTP 에서도 고른 계정의 메일 주소가 한 번에 복사된다', async () => {
  plainHttp()
  page()
  await screen.findByText('kim@example.local')
  expect(screen.getByRole('button', { name: /메일 주소 복사/ })).toBeDisabled()

  fireEvent.click(screen.getByRole('checkbox', { name: '전체 선택' }))
  fireEvent.click(screen.getByRole('button', { name: '메일 주소 복사 (3)' }))
  await waitFor(() => expect(copied).toEqual(['kim@example.local; lee@example.local']))
  expect(screen.getByRole('status').textContent).toMatch(/메일 주소 2개를 복사했습니다.*아이디 1개\(admin\)는 제외/)

  // 하나만 고르면 그것만.
  fireEvent.click(screen.getByRole('checkbox', { name: '전체 선택' }))
  fireEvent.click(screen.getByRole('checkbox', { name: 'lee@example.local 선택' }))
  fireEvent.click(screen.getByRole('button', { name: '메일 주소 복사 (1)' }))
  await waitFor(() => expect(copied.at(-1)).toBe('lee@example.local'))
})

test('브라우저가 복사를 막으면 주소를 골라 둔 채로 보여 준다 — 직접 Ctrl+C', async () => {
  plainHttp(false)
  page()
  fireEvent.click(await screen.findByRole('checkbox', { name: '전체 선택' }))
  fireEvent.click(screen.getByRole('button', { name: '메일 주소 복사 (3)' }))
  const box = (await screen.findByLabelText('복사할 메일 주소')) as HTMLTextAreaElement
  expect(box.value).toBe('kim@example.local; lee@example.local')
  expect(screen.getByText(/Ctrl\+C/)).toBeInTheDocument()
})

test('보안 문맥에서 clipboard 가 거절해도 한 번 더 해 본다', async () => {
  plainHttp()
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText: vi.fn(async () => Promise.reject(new Error('NotAllowedError'))) },
  })
  page()
  fireEvent.click(await screen.findByRole('checkbox', { name: 'kim@example.local 선택' }))
  fireEvent.click(screen.getByRole('button', { name: '메일 주소 복사 (1)' }))
  await waitFor(() => expect(copied).toEqual(['kim@example.local']))
})
