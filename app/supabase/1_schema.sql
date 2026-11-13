-- 본과 1학년 앱 — Supabase 표와 보안 규칙
-- Supabase 대시보드 → SQL Editor → New query 에 이 파일 전체를 붙여넣고 Run. (여러 번 돌려도 안전)

-- 1) 표 -----------------------------------------------------------------------
create table if not exists public.members (           -- 들어올 수 있는 사람 (GitHub 아이디, 소문자)
  login text primary key check (login = lower(login)),
  role  text not null default 'member' check (role in ('owner','editor','member')),
  created_at timestamptz not null default now()
);
create table if not exists public.docs (              -- 평가·후기·총평·메모 (아티팩트 db 와 같은 모양)
  collection text not null,                            -- reviews, courseNotes, sem1, memos
  scope      text not null default '',                 -- '' = 모두가 보는 것, GitHub 아이디 = 그 사람만 (memos)
  id         text not null,
  data       jsonb not null default '{}'::jsonb,
  updated_by text,
  updated_at timestamptz not null default now(),
  primary key (collection, scope, id)
);

-- 2) 로그인한 사람이 누구인지 — 사용자가 고칠 수 없는 auth.identities(GitHub 가 준 값)에서 읽는다
create or replace function public.my_login() returns text
language sql stable security definer set search_path = '' as $$
  select lower(coalesce(i.identity_data->>'user_name', i.identity_data->>'preferred_username'))
  from auth.identities i
  where i.user_id = auth.uid() and i.provider = 'github'
  limit 1
$$;
create or replace function public.my_role() returns text
language sql stable security definer set search_path = '' as $$
  select m.role from public.members m where m.login = public.my_login()
$$;
revoke all on function public.my_login() from public, anon;
revoke all on function public.my_role()  from public, anon;
grant execute on function public.my_login() to authenticated;
grant execute on function public.my_role()  to authenticated;

-- 3) 권한 ---------------------------------------------------------------------
revoke all on public.members, public.docs from anon;
grant select, insert, update, delete on public.members, public.docs to authenticated;
alter table public.members enable row level security;
alter table public.docs    enable row level security;

drop policy if exists "members read"  on public.members;
drop policy if exists "members admin" on public.members;
create policy "members read"  on public.members for select to authenticated
  using (public.my_role() is not null);                                  -- 회원만 회원 목록을 본다
create policy "members admin" on public.members for all to authenticated
  using (public.my_role() = 'owner') with check (public.my_role() = 'owner');   -- 관리자만 추가·변경·삭제

drop policy if exists "docs read"   on public.docs;
drop policy if exists "docs mine"   on public.docs;
drop policy if exists "docs shared" on public.docs;
create policy "docs read" on public.docs for select to authenticated
  using (public.my_role() is not null and (scope = '' or scope = public.my_login()));
create policy "docs mine" on public.docs for all to authenticated      -- 내 메모는 회원 누구나
  using      (public.my_role() is not null and scope <> '' and scope = public.my_login())
  with check (public.my_role() is not null and scope <> '' and scope = public.my_login());
create policy "docs shared" on public.docs for all to authenticated    -- 평가·후기·총평은 관리자·후기 작성자만
  using      (scope = '' and public.my_role() in ('owner','editor'))
  with check (scope = '' and public.my_role() in ('owner','editor'));

-- 4) 관리자 -------------------------------------------------------------------
insert into public.members (login, role) values ('evenstar1031', 'owner')
on conflict (login) do update set role = 'owner';
