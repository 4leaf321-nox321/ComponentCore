import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import { TokensPanel } from '@/modules/auth/TokensPanel'

const TOKEN = {
  id: 't1',
  name: 'Claude Code',
  prefix: 'autojig_pat_ab',
  scopes: ['read', 'write'],
  created_at: '2026-09-01T00:00:00Z',
  expires_at: null,
  last_used_at: null,
  revoked_at: null,
}

test('만료일은 날짜로 고르고, 발급한 토큰이 도구별 등록 형식에 채워진다', async () => {
  const calls: { url: string; body: unknown }[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input)
    calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null })
    const body = url.endsWith('/auth/tokens') && init?.method === 'POST'
      ? { token: 'autojig_pat_SECRET', pat: TOKEN }
      : url.endsWith('/auth/tokens')
        ? [TOKEN]
        : url.endsWith('/auth/token-scopes')
          ? { scopes: ['read', 'write'], descriptions: {} }
          : { url: '', port: 8062, server_name: 'autojig' }
    return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })
  render(<TokensPanel />)
  // 토큰 없이도 등록 형식이 보인다 — 자리표시자로.
  expect((await screen.findAllByText(/<발급받은_토큰>/)).length).toBeGreaterThan(0)
  expect(screen.getByText(/claude mcp add --transport http autojig/)).toBeInTheDocument()

  // 이름 빠른 선택 · 만료일 30일 · 발급.
  fireEvent.click(screen.getByRole('button', { name: 'Gemini CLI' })) // 탭이 아니라 이름 빠른 선택
  expect(screen.getByLabelText(/^이름/)).toHaveValue('Gemini CLI')
  fireEvent.click(screen.getByRole('button', { name: '30일' }))
  const date = (screen.getByLabelText(/만료일/) as HTMLInputElement).value
  expect(date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  fireEvent.click(screen.getByRole('button', { name: '토큰 발급' }))
  await waitFor(() => expect(screen.getByText(/토큰이 발급되었습니다/)).toBeInTheDocument())
  const sent = calls.find((c) => c.url.endsWith('/auth/tokens') && c.body)!.body as { expires_in_days: number; name: string }
  expect(sent.name).toBe('Gemini CLI')
  expect(sent.expires_in_days).toBeGreaterThanOrEqual(29)
  expect(sent.expires_in_days).toBeLessThanOrEqual(31)

  // 발급한 이름이 Gemini 라 Gemini 탭이 먼저 열리고, 실제 토큰이 채워져 있다.
  await waitFor(() => expect(screen.getByRole('tab', { name: 'Gemini CLI' })).toHaveAttribute('aria-selected', 'true'))
  expect(screen.getByText(/"httpUrl": "http:\/\/localhost:8062\/mcp"/)).toBeInTheDocument()
  expect(screen.getAllByText(/autojig_pat_SECRET/).length).toBeGreaterThan(0)

  // 만료 「없음」 이면 날짜가 비고 null 로 간다.
  fireEvent.click(screen.getByRole('button', { name: '없음' }))
  expect(screen.getByLabelText(/만료일/)).toHaveValue('')
})
