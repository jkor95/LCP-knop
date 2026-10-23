# Vier SONOFF SNZB-04PR2-deursensoren

De webapp en Supabase-instellingen worden online bijgewerkt. De lokale worker
moet eenmalig op de **bestaande Windows-werklaptop** worden bijgewerkt.

## Standaardinstellingen

| Zigbee2MQTT-naam | Openen | Sluiten | Na 5 minuten open |
| --- | --- | --- | --- |
| LCP kantoor | Aan | Aan | Uit |
| LCP nooddeur | Aan | Aan | Aan |
| TRAP nooddeur | Aan | Aan | Aan |
| LCP reserve | Uit | Uit | Uit |

De twee nooddeuren hebben daarnaast standaard een tweede waarschuwing na
**10 minuten onafgebroken open**, gerekend vanaf openen. De beheerpagina heeft
hiervoor een eigen tijd en tekst. Met 0 minuten schakel je die tweede melding uit.
Sluiten annuleert beide timers. Per open/sluitcyclus worden maximaal twee
tijdswaarschuwingen verstuurd.

De drie actieve sensoren melden 24 uur per dag, 7 dagen per week. De reserve
blijft gekoppeld en uitgeschakeld. De namen hierboven moeten exact overeenkomen
met de bestaande Friendly names in Zigbee2MQTT, inclusief spaties. Op de
beheerpagina pas je de **Naam in LCP** vrij aan; de bestaande Zigbee-koppeling
blijft vaststaan. Per deur kun je openen/sluiten, de timer, teksten en meldtijden
apart instellen. Kies **Volgens weekschema** voor optionele tijdvakken.

## Sabotagecontact

De SONOFF SNZB-04PR2 publiceert via Zigbee2MQTT de booleaanse eigenschap `tamper`.
Voor de drie actieve sensoren staat een sabotagemelding standaard aan; voor de
reserve staat die uit. Op de beheerpagina kun je dit per sensor uitschakelen en
de meldingstekst aanpassen. `{naam}` wordt vervangen door de naam in LCP.

Sabotagemeldingen gelden 24 uur per dag, onafhankelijk van de deurstand en het
weekschema, zolang het apparaat actief is. Alleen een bevestigde overgang van
`tamper: false` naar `tamper: true` geeft een melding. Herhaalde statusberichten
geven geen extra melding; herstel naar false maakt een nieuw incident mogelijk.
Ook berichten zonder deurstand worden verwerkt. De eerste actuele status na
opstarten of een verbindingsonderbreking vormt alleen de uitgangsstatus; een
bewaard MQTT-bericht geeft geen alarm. Een ontbrekende eigenschap wordt niet
als veilig beschouwd. Het contact detecteert sabotage van de behuizing, niet
gegarandeerd iedere manier waarop de sensor van de deur kan worden verwijderd.

Test na de update eerst de normale knop/deuren. Controleer daarna bij een
bevestigde normale sabotagestatus voorzichtig het sabotagecontact van de
behuizing en herstel dit weer. Forceer de behuizing of bevestiging niet. Laat
dit achterwege als de sensor nog niet veilig toegankelijk is. Controleer in
Zigbee2MQTT of `tamper` daadwerkelijk van false naar true verandert en of de
iPhone één melding ontvangt.

## Eenmalig bijwerken op de werklaptop

1. Meld je aan met **hetzelfde Windows-account** waarmee LCP normaal draait.
   Sluit de laptop aan op stroom, laat Zigbee2MQTT en MQTT draaien en zorg voor
   internet. Gebruik geen ander beheerdersaccount: de bestaande DPAPI-aanmelding
   hoort bij je huidige account.
2. Download [het Windows-updatepakket](../downloads/LCP-deursensor-update.zip)
   en kies in Verkenner **Alles uitpakken**. Pak het uit in Downloads, buiten
   `%LOCALAPPDATA%\LCP\Werklaptop`.
3. Dubbelklik op **Update-LCP-Deursensoren.cmd** in de uitgepakte map.
4. De update maakt eerst een gecontroleerde back-up onder
   `%LOCALAPPDATA%\LCP\Werklaptop\worker-backups`.
   Bij jouw **Opstarten-snelkoppeling** verschijnt **Update voorbereid. Herstart
   Windows om de vier deursensoren te activeren.** Sla je werk op, herstart
   Windows en meld je aan met hetzelfde account. Wacht een minuut en open
   **Controleer-LCP-Deursensoren.cmd** uit het uitgepakte pakket. Er moet
   **Actief: nieuwe sensorworker, MQTT verbonden en alle vier deursensoren
   geladen** verschijnen. De bestaande achtergrondstarter en MQTT-aanmelding
   blijven behouden; de updater stopt geen processen en start geen tweede worker.
   Bij een installatie via Taakplanner herstart de updater alleen de bestaande
   taak en wacht op **Update voltooid**; een mislukte start wordt teruggedraaid.
5. Druk op de bestaande LCP-knop. Controleer dat je gewone iPhone-melding met
   de bestaande knoptekst aankomt.
6. Beweeg elke actieve deur eenmaal en sluit hem weer om de actuele
   uitgangsstatus te bevestigen. Open en sluit daarna nogmaals: controleer beide
   meldingen. Laat iedere nooddeur vijf en daarna tien minuten open om beide
   waarschuwingen te controleren. Sluiten binnen vijf minuten annuleert beide;
   sluiten tussen vijf en tien minuten annuleert de tweede.

De update herkent de bestaande Python-worker, MQTT-host, poort, basistopic en
bijbehorende starttaak. Zij behoudt de bestaande starter, DPAPI-inloggegevens en
taakinstellingen. Alleen de worker en een apart bestand met runtime-instellingen
worden geplaatst. De Zigbee-database, coordinator-back-up, Zigbee2MQTT-configuratie,
USB-dongle en COM3 worden niet vervangen. Er wordt geen tweede worker gestart.

Als Windows onvoldoende rechten voor de bestaande starttaak meldt, start het
updatebestand als beheerder **met hetzelfde Windows-account**.

Als worker, inlogmethode, extra MQTT-beveiliging of starttaak niet herkenbaar is,
**stopt de update zonder vervanging**. Bewaar dan de zichtbare melding. Een
installatie met een afwijkende beveiligde aanmelding moet eerst daarop worden
aangepast; ga niet opnieuw installeren en koppel de sensoren niet opnieuw.

## Herstel

### Starttaak of installatiemap niet herkend

Uitpakken in Downloads is goed: de update zoekt de bestaande installatie apart.
Een map `LCP-knop-main` kan een uitgepakte broncodedownload zijn en hoeft niet
de actieve installatie te zijn. Verplaats geen bestanden om de controle te omzeilen.

Open **Controleer-LCP-Start.cmd** in het uitgepakte pakket. Vul desgevraagd het
pad van je andere LCP-map in, of druk op Enter. Dit leest de starttaken,
Python-startbestanden en opstartsnelkoppelingen en schrijft **LCP-startcontrole.txt**
naast het controlebestand. Het verandert geen taken of installatiebestanden en
neemt geen wachtwoorden, tokens of overige opdrachtargumenten op. Deel de tekst
uit dit verslag om de werkelijke startmethode te laten controleren.
Als `support/account.py` aanwezig is, leest de controle ook de Python-structuur
van die starter zonder hem uit te voeren. Vaste waarden worden afgeschermd;
alleen vooraf toegestane bestandsnamen en technische sleutelnamen blijven staan.
Inlogbestanden worden niet geopend. De updater ondersteunt de herkende
Opstarten-installatie met `support/account.py` en `support/upstream_worker.py`.
Hij behoudt de starter en diens MQTT-aanmelding. De nieuwe worker krijgt een
afzonderlijk v3-statusbestand; het oude statusbestand wordt niet overschreven.

Bij de Taakplanner-installatie zet de update na een mislukte start de vorige
worker terug en start zij de bestaande taak opnieuw. Bij de Opstarten-installatie
kan die controle pas na de Windows-herstart gebeuren. Voor handmatig
herstel kun je **Herstel-LCP-Worker.cmd** uit hetzelfde uitgepakte pakket openen.
Dit zet de laatste gecontroleerde workerback-up terug. Bij Opstarten moet je
Windows daarna opnieuw starten. Test daarna de bestaande
LCP-knop. De Zigbee-database wordt ook bij herstel niet gewijzigd.

## Status na herstart of onderbreking

- `contact: true` betekent dicht; `contact: false` betekent open.
- De eerste verse status na opstarten, MQTT-herstel of een gemelde Zigbee-
  onderbreking is alleen een uitgangsstatus. Er wordt geen oud open/dichtbericht
  opnieuw verstuurd. Een bewaarde MQTT-status start geen timer.
- Een vijfminutentimer gebruikt een monotone klok en begint pas bij een actuele
  waargenomen openstatus. Offline tijd wordt niet achteraf als open tijd geteld.
- Een reeds verstuurde vijfminutenwaarschuwing wordt bij dezelfde bewaarde
  openstatus niet nog eens verstuurd. Een nieuwe waargenomen sluiting en opening
  beginnen een nieuwe cyclus.
- Herhaalde identieke statusberichten veroorzaken geen extra meldingen. Bij een
  verloren HTTP-antwoord wordt dezelfde gebeurtenissleutel hergebruikt; Supabase
  maakt daarmee maximaal één oproep en één pushopdracht aan.
- Niet bevestigde gebeurtenissen worden na een nieuwe MQTT-sessie of workerstart
  niet achteraf afgespeeld. Bewegingen terwijl de laptop of Zigbee offline is,
  kunnen niet betrouwbaar worden gereconstrueerd.
- De timer wordt geannuleerd bij sluiten. Met **Gebruik de ingestelde meldtijden
  ook voor de waarschuwing** geldt het weekschema ook voor de timer. Bestaande,
  oudere sensorinstellingen behouden hun eerdere onafhankelijke timergedrag.

De instellingen worden circa elke 15 seconden opgehaald. Het lokale statusbestand
is `sensor_state_v3.json`; `sensor_worker_health.json` bevestigt versie,
MQTT-verbinding en opgehaalde apparaatnamen. Deze bestanden bevatten geen
wachtwoorden of tokens. De bestaande pushregistraties en alarmtoon blijven gelijk.
