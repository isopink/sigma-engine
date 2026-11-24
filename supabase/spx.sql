-- 11-25 S.Lee: S&P 500 선물(ES=F) 실시간 시세를 Supabase 안에서 1분마다 수집 (PC를 켜 둘 필요 없음)
-- 대시보드 누적 수익률 차트의 S&P 500 끝점 = 직전 S&P 500 종가 × (선물 지금 가격 / 선물 전 거래일 종가)
-- 한국 장중에도 선물은 움직여서 S&P 500 선이 실시간으로 바뀜. 지난 날짜는 그대로 docs/data/spx.json (종가)
-- Supabase → SQL Editor → New query 에 전체를 붙여넣고 Run (비밀문구 없음, 다시 실행해도 안전함)

create extension if not exists pg_net;
create extension if not exists pg_cron;

create table if not exists public.spx_ticks (
  ts         timestamptz primary key,   -- 시세 시각 (Yahoo regularMarketTime)
  price      numeric not null,          -- 선물 지금 가격
  prev_close numeric                    -- 선물 전 거래일 종가
);
alter table public.spx_ticks enable row level security;
revoke all on public.spx_ticks from anon, authenticated;
grant select on public.spx_ticks to anon;            -- 사이트는 읽기만
drop policy if exists "anyone reads spx" on public.spx_ticks;
create policy "anyone reads spx" on public.spx_ticks for select to anon using (true);

-- 보낸 요청 번호와 마지막 응답 상태 (응답은 다음 회차에 꺼냄)
create table if not exists public.spx_req (id bigint primary key, at timestamptz not null default now(), status int);
alter table public.spx_req enable row level security;
revoke all on public.spx_req from anon, authenticated;

create or replace function public.spx_collect()
returns void language plpgsql security definer set search_path = public as $$
declare r record; m jsonb;
begin
  -- 1) 지난 회차 응답 저장
  for r in select q.id, h.status_code, h.content from public.spx_req q join net._http_response h on h.id = q.id loop
    begin
      m := r.content::jsonb -> 'chart' -> 'result' -> 0 -> 'meta';
      if r.status_code = 200 and (m ->> 'regularMarketPrice') is not null then
        insert into public.spx_ticks (ts, price, prev_close)
        values (to_timestamp((m ->> 'regularMarketTime')::bigint), (m ->> 'regularMarketPrice')::numeric,
                coalesce((m ->> 'chartPreviousClose')::numeric, (m ->> 'previousClose')::numeric))
        on conflict (ts) do update set price = excluded.price, prev_close = excluded.prev_close;
      end if;
    exception when others then null;   -- 응답이 JSON 이 아니면 (차단 · 오류 페이지) 건너뜀
    end;
    delete from public.spx_req where id = r.id;
  end loop;
  delete from public.spx_req where at < now() - interval '10 minutes';
  delete from public.spx_ticks where ts < now() - interval '3 days';
  -- 2) 다음 회차 요청
  insert into public.spx_req (id) select net.http_get(
    'https://query1.finance.yahoo.com/v8/finance/chart/ES=F?range=1d&interval=1d',
    headers := '{"User-Agent": "Mozilla/5.0"}'::jsonb);
end $$;
revoke all on function public.spx_collect() from public, anon, authenticated;

-- 매분 (선물은 미국 시각 일~금 거의 24시간 거래)
select cron.unschedule('spx') where exists (select 1 from cron.job where jobname = 'spx');
select cron.schedule('spx', '* * * * *', 'select public.spx_collect()');
select public.spx_collect();   -- 지금 한 번 요청 (1~2분 뒤 spx_ticks 에 첫 줄)

-- 확인: select * from public.spx_ticks order by ts desc limit 3;
