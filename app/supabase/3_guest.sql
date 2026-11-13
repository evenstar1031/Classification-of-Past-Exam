-- 본과 1학년 앱 — 로그인 없이 둘러보기(손님)가 평가·후기·총평을 읽을 수 있게 (2026-11-13)
-- 이미 1_schema.sql 을 돌린 프로젝트에 이것만 Run. 메모와 회원 목록은 계속 회원만.
grant select on public.docs to anon;
drop policy if exists "docs guest read" on public.docs;
create policy "docs guest read" on public.docs for select to anon
  using (scope = '');
