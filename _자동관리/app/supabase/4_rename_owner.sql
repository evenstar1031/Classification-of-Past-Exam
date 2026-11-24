-- GitHub 아이디를 evenstar1031 → seohoe1031 로 바꾼 뒤 한 번 실행 (2026-11-24)
-- Supabase → SQL Editor 에 붙여 넣고 Run. 회원 명단·내 메모(scope)를 새 아이디로 옮긴다.
begin;
insert into public.members (login, role)
  select 'seohoe1031', role from public.members where login = 'evenstar1031'
  on conflict (login) do update set role = excluded.role;
update public.docs set scope = 'seohoe1031' where scope = 'evenstar1031';
delete from public.members where login = 'evenstar1031';
commit;
-- 확인: 아래 두 줄이 각각 owner 1줄, 0 이 나오면 끝
select login, role from public.members where login in ('seohoe1031', 'evenstar1031');
select count(*) as 남은_옛아이디 from public.docs where scope = 'evenstar1031';
