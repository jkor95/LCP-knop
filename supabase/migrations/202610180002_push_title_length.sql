-- Het titelveld en de RPC staan 100 tekens toe. De oorspronkelijke tabel
-- begrensde dit tot 90, waardoor een geldige invoer alsnog kon mislukken.
-- Verruim uitsluitend deze grens; bestaande teksten en rechten blijven behouden.
begin;
alter table public.lcp_push_preferences drop constraint if exists lcp_push_preferences_title_check;
alter table public.lcp_push_preferences add constraint lcp_push_preferences_title_check
 check (char_length(btrim(title)) between 1 and 100);
commit;
