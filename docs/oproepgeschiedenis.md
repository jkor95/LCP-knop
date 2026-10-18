# Oproepgeschiedenis

Onder **Laatste oproepen** kan de beheerder met **Geschiedenis resetten** de
zichtbare lijst voor alle LCP-gebruikers leegmaken. Nieuwe oproepen verschijnen
daarna vanzelf. Gewone gebruikers kunnen de geschiedenis niet resetten.

Elke maandag om 00.00 uur (nacht van zondag op maandag) in `Europe/Amsterdam` begint de lijst opnieuw. Dit is
een serverberekende ondergrens, geen taak die een geopende app nodig heeft.
Ook na een week zonder appgebruik geldt meteen de juiste maandaggrens.
Zomer- en wintertijd worden door PostgreSQL verwerkt. Een geopende app ververst
de lijst iedere acht seconden en bij terugkeer naar de app.

De effectieve grens is de laatste maandag of een latere handmatige reset.
De bestaande SELECT-rechten en RLS op `lcp_calls` blijven gelden. Alleen de
aparte, afgeschermde tabel `lcp_call_history_state` bewaart het resetmoment.
De oproeprecords zelf blijven intern bewaard; resetten verwijdert geen oproepen
en wijzigt geen afhandeling, alarm, pushregistratie, trigger of Windows-worker.

Activering: pas `supabase/migrations/202610180003_call_history.sql` toe na de
bestaande pushmigraties. De bestaande GitHub-workflow **LCP Supabase activeren**
doet dit automatisch en controleert de rechten met een teruggedraaide reset.
