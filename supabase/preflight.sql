-- Alleen-lezen controle vóór de migratie. Bevat geen tokens of abonnementssleutels.
select column_name,data_type,is_nullable,column_default from information_schema.columns
where table_schema='public' and table_name in('lcp_push_preferences','lcp_members','lcp_push_subscriptions') order by table_name,ordinal_position;
select id,title,icon_url,updated_at from public.lcp_push_preferences;
select schemaname,tablename,policyname,permissive,roles,cmd,qual,with_check from pg_policies
where (schemaname='public' and tablename in('lcp_push_preferences','lcp_push_subscriptions','lcp_members')) or (schemaname='storage' and tablename='objects');
select id,name,public,file_size_limit,allowed_mime_types from storage.buckets where id='lcp-branding';
select tgname,pg_get_triggerdef(oid) from pg_trigger where tgrelid='public.lcp_calls'::regclass and not tgisinternal;
-- Inspecteer daarnaast de bestaande push-Edge Function en webhook in het dashboard.
