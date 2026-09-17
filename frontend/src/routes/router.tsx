/**
 * 라우트 표. 사이드바(navigation.ts)에 있는 항목은 여기에 대응 경로가 있어야 한다 —
 * `router.test.tsx` 가 검사한다. /login · /force-password-change 만 가드 밖이다.
 */

import { lazy } from 'react'
import { Navigate, createBrowserRouter } from 'react-router-dom'

import ForcePasswordChangePage from '@/modules/auth/ForcePasswordChangePage'
import LoginPage from '@/modules/auth/LoginPage'
import { ROUTER_BASENAME } from '@/shared/base'
import { ProtectedRoute } from '@/shared/auth/ProtectedRoute'
import { Placeholder } from '@/shared/components/Placeholder'
import { AppShell } from '@/shared/layout/AppShell'

// **매일 밟는 길(로그인 · 프로젝트 목록)은 처음에 싣고** 나머지는 나눠 싣는다.
const JigProjectsPage = lazy(() => import('@/modules/jigs/JigProjectsPage'))
const JigProjectPage = lazy(() => import('@/modules/jigs/JigProjectPage'))
const CadWorkbenchPage = lazy(() => import('@/modules/cad/CadWorkbenchPage'))
const ProfilePage = lazy(() => import('@/modules/auth/ProfilePage'))
const AccountsAdminPage = lazy(() => import('@/modules/accounts/AccountsAdminPage'))
const ServerPage = lazy(() => import('@/modules/server/ServerPage'))

export const router = createBrowserRouter(
  [
    { path: '/login', element: <LoginPage /> },
    {
      element: <ProtectedRoute />,
      children: [
        { path: '/force-password-change', element: <ForcePasswordChangePage /> },
        {
          path: '/',
          element: <AppShell />,
          children: [
            { index: true, element: <Navigate to="/jigs" replace /> },
            { path: 'jigs', element: <JigProjectsPage /> },
            { path: 'jigs/:id', element: <JigProjectPage /> },
            { path: 'cad', element: <CadWorkbenchPage /> },
            { path: 'me', element: <ProfilePage /> },
            { path: 'admin/accounts', element: <AccountsAdminPage /> },
            { path: 'admin/server', element: <ServerPage /> },
            {
              path: '*',
              element: (
                <Placeholder title="없는 페이지" phase="—" description="주소를 확인해 주세요." />
              ),
            },
          ],
        },
      ],
    },
  ],
  { basename: ROUTER_BASENAME },
)
