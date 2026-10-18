# Pushmeldingen beheren

Open **Apparaten en meldingen** vanuit de LCP-webapp. Alleen beheerders kunnen deze pagina gebruiken.

1. Pas onder **Pushmeldingen** de titel, appnaam en standaardtekst voor nieuwe knoppen aan. De standaardwaarden zijn **LCP – Oproep**, **LCP** en **Er is op de oproepknop gedrukt.** Bestaande voorkeuren worden behouden.
2. Kies eventueel een PNG-logo. Bekijk het voorbeeld en klik op **Pushinstellingen opslaan**. Een gekozen bestand wordt pas bij opslaan geüpload. **Standaardlogo herstellen** wordt ook pas na opslaan definitief.
3. Kies onder **Gekoppelde apparaten** een knop of deur. Wijzig **Naam in LCP** of de bestaande apparaatteksten en klik op **Instellingen opslaan**. De gekoppelde Zigbee2MQTT-naam blijft bij bestaande apparaten vaststaan. Knopdruk, deur openen en deur te lang open hebben afzonderlijke teksten. `{minuten}` blijft werken voor de lange-openmelding.
4. Kies bij **Voorbeeld pushmelding** de standaardmelding of een bericht van het geselecteerde apparaat. Het voorbeeld toont ook nog niet opgeslagen tekstwijzigingen.
5. **Testmelding versturen** verstuurt alleen naar de geregistreerde apparaten van het eigen ingelogde beheerdersaccount. Een iPhone onder een ander account ontvangt die test niet. Er wordt geen rij in `lcp_calls` aangemaakt. Een nieuwe logo-upload moet vóór deze test worden opgeslagen. Maximaal één test per 30 seconden.

Open LCP op ieder ontvangend apparaat na het wijzigen van de instellingen. De webapp bewaart de algemene pushweergave in de serviceworker, zodat oudere pushafzenders blijven werken. Actuele voorkeuren uit een bijgewerkte serverpayload gaan voor op deze lokale kopie. Een apparaat dat gesloten blijft, houdt zonder die serveruitbreiding de laatst opgehaalde titel en het logo.

## iPhone

- Open de bestaande LCP-webapp vanaf het beginscherm. Laat deze eenmaal de nieuwe versie ophalen.
- Bestaande pushregistraties worden niet verwijderd of opnieuw aangemaakt door deze update. De bestaande VAPID-sleutel blijft behouden.
- Controleer de ontvangst met een persoonlijke test. ‘Aangeboden’ betekent dat de pushdienst de melding heeft geaccepteerd, niet dat iOS deze al heeft getoond.
- iOS bepaalt de systeemtekst, het pushgeluid en de uiteindelijke vormgeving. Een door iOS toegevoegd woord zoals ‘from’ is niet met appcode te verwijderen. De appnaam is standaard kort: **LCP**.
- Het beginschermicoon kan door iOS worden bewaard. Als je dit wilt bijwerken, moet je de webapp mogelijk opnieuw toevoegen. Schakel meldingen daarna opnieuw in. Doe dit niet alleen om de titel of berichttekst te wijzigen.
- Het bestaande instelbare LCP-alarm blijft ongewijzigd werken wanneer de webapp open is. Bij een gesloten app gebruikt iOS zijn eigen meldingsgeluid.

## Supabase activeren (eenmalig, voor projectbeheer)

Deze repository bevat de aanvullende serverfunctie en een migratie. Het publiceren van GitHub Pages voert die **niet** uit. Controleer vóór activering de bestaande Supabase-installatie met beheerstoegang; de openbare API kan geen RLS-regels, functiecode of geheime bindingen inspecteren. Een leeg anoniem antwoord betekent niet dat gegevens of een bucket ontbreken.

1. Voer `supabase/preflight.sql` alleen-lezen uit. Inspecteer de bestaande pushfunctie, de webhook op `lcp_calls`, de policies van `lcp_members` en `lcp_push_subscriptions`, en de bucket `lcp-branding`. Bewaar de bestaande voorkeuren en functiedefinitie als herstelpunt buiten de publiek gepubliceerde bestanden. Exporteer geen abonnementssleutels of credentials naar Git.
2. Controleer dat `lcp_push_preferences` één algemene rij bevat en `id`, `title`, `icon_url` en `updated_at` heeft. De migratie hergebruikt de bestaande rij, id en voorkeuren. Bij meerdere rijen stopt de migratie volledig; onderzoek dan eerst het bestaande model. Een bestaande privébucket wordt niet automatisch openbaar gemaakt.
3. Voer `supabase/migrations/202610180001_push_settings.sql` transactioneel uit. Deze voegt `default_message` en `app_name`, de beveiligde lees-/schrijffuncties en opslagregels toe. Een ontbrekende bucket wordt alleen via `ON CONFLICT DO NOTHING` aangemaakt. Bestaande bucketinstellingen en policies worden behouden; extra restrictieve regels begrenzen wijzigingen aan beheerders. De bestaande service-role-pushafzender behoudt toegang. Wijzig geen RLS op oproepen, apparaten of abonnementen zonder de bestaande stroom eerst te onderzoeken.
4. De bestaande pushregistraties vereisen de **bestaande** VAPID-sleutels. Maak geen nieuwe sleutels. De nieuwe functie verwacht projectsecrets `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` en `VAPID_SUBJECT`. Hergebruik de bestaande projectbindingen; staan ze onder andere namen, pas dan uitsluitend de serververwijzingen in `supabase/functions/lcp-push-test/index.ts` aan. De private sleutel wordt nooit naar de browser gestuurd. De functie weigert te starten als de publieke sleutel afwijkt van de al gebruikte sleutel.
5. Publiceer alleen de aanvullende functie: `supabase functions deploy lcp-push-test --project-ref jrlcofhpxvnlqzirjdbd`. `verify_jwt=false` schakelt alleen de oudere gatewaycontrole uit; de functie controleert zelf verplicht iedere gebruikerssessie met `auth.getUser`, controleert de beheerdersrol en selecteert abonnementen uitsluitend met `user_id = geverifieerde_gebruiker`. Zij accepteert geen ontvangende gebruikers-id of algemene verzendmodus.
6. Voor direct bijgewerkte voorkeuren bij **gesloten** apps: laat de bestaande pushafzender de algemene voorkeuren naast het bestaande `message`-veld meesturen, zonder de doelgroep, webhook of opslag van oproepen te wijzigen:

   ```js
   {
     id: call.id,
     message: call.message,
     lcp_preferences: { title, default_message, app_name, icon_url }
   }
   ```

   Lees de rij met de bestaande serverauthenticatie. Houd een Nederlandse standaardmelding aan als voorkeuren tijdelijk niet kunnen worden gelezen. Vervang de bestaande afzender niet door de persoonlijke testfunctie: die is bewust alleen voor eigen registraties. Wanneer de originele servercode niet beschikbaar is, blijft de lokale serviceworker-terugval bruikbaar na eenmaal openen, maar is actuele weergave voor blijvend gesloten apparaten niet gegarandeerd.
7. Controleer in productie met een beheerdersaccount: laden, opslaan, logo-upload, herstel standaardlogo en de persoonlijke iPhone-test. Controleer met een gewoon lid dat lezen/ontvangen lukt en schrijven/uploaden wordt geweigerd. Controleer dat een test geen andere gebruiker bereikt. Test de fysieke SONOFF-knop en de deursensor op de bestaande Windows-laptop. Een automatische browsertest met nagebootste diensten is geen bewijs van productiebezorging.

De migratie wijzigt geen `lcp_calls`, `lcp_devices`, `lcp_push_subscriptions`, Windows-worker, Zigbee2MQTT, MQTT-instellingen, taken of alarmlogica. De persoonlijke testfunctie verwijdert ook verlopen registraties niet. Logo's krijgen een unieke bestandsnaam; eerdere logo's blijven behouden voor bestaande clients.

## Automatische controles

- `node --test tests/push.test.mjs`: Nederlandse terugval, logo-URL's en beveiliging van persoonlijke tests.
- `node --test tests/push-database.test.mjs`: de echte migratie, behoud van bestaande gegevens, RLS, bevoegdheden en limiet voor tests. Vereist `@electric-sql/pglite@0.3.14`; `LCP_PGLITE_MODULE` kan naar een installatie buiten de checkout wijzen.
- `LCP_BROWSER_TESTS=1 python -m unittest discover -s tests -p test_push_ui.py -v`: Chromium, echte DOM en serviceworker met nagebootste Supabase. Vereist Playwright en een geïnstalleerde browser; `CHROMIUM_PATH` kan een systeembrowser aanwijzen.
- `python -m unittest discover -s tests -p test_lcp_sensors.py -v`: de bestaande vijf tests voor knop, deur en beveiligingsschema.

GitHub Actions voert deze controles automatisch uit. Er worden daarbij geen productiepushmeldingen verstuurd.

## Alternatief als Codex het geheim niet kan opslaan

Voeg het bestaande Supabase-toegangstoken uitsluitend toe als GitHub Actions-geheim `SUPABASE_ACCESS_TOKEN` bij deze repository (Settings → Secrets and variables → Actions). Zet de waarde nooit in code, een issue of chat. Dit omzeilt de vastlopende Codex-editor; er is geen nieuwe Supabase-sleutel nodig.

De handmatig te starten workflow **LCP Supabase controleren** gebruikt het token alleen tegen de beheer-API van project `jrlcofhpxvnlqzirjdbd`. Hij leest het bestaande schema, policies, algemene pushvoorkeuren en relevante servercode. Hij wijzigt geen databasegegevens, verstuurt geen pushmeldingen en schrijft geen credentialwaarden naar de log. Secretmetadata wordt tot namen beperkt.

Het rapport wordt met een openbare controlesleutel versleuteld en één dag als GitHub Actions-artifact bewaard. Een versleutelde kopie op de afzonderlijke branch `lcp-supabase-rapport` maakt ophalen mogelijk wanneer het artifactdomein door de cloudomgeving wordt geblokkeerd. Deze workflow mag daarvoor alleen het versleutelde rapport schrijven; hij verandert geen appbestanden op `main`. De privésleutel staat buiten de repository in de actieve Codex-werkruimte. De openbare sleutel in `.github/supabase-review-public.pem` is geen credential. Gaat de privésleutel verloren, maak dan een nieuw sleutelpaar en voer de controle opnieuw uit. Activering van de migratie en serverfunctie volgt pas na beoordeling van de bestaande installatie.
