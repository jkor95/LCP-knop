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

De drie actieve sensoren melden 24 uur per dag, 7 dagen per week. De reserve
blijft gekoppeld en uitgeschakeld. De namen hierboven moeten exact overeenkomen
met de bestaande Friendly names in Zigbee2MQTT, inclusief spaties. Op de
beheerpagina pas je de **Naam in LCP** vrij aan; de bestaande Zigbee-koppeling
blijft vaststaan. Per deur kun je openen/sluiten, de timer, teksten en meldtijden
apart instellen. Kies **Volgens weekschema** voor optionele tijdvakken.

## Eenmalig bijwerken op de werklaptop

1. Meld je aan met **hetzelfde Windows-account** waarmee LCP normaal draait.
   Sluit de laptop aan op stroom, laat Zigbee2MQTT en MQTT draaien en zorg voor
   internet. Gebruik geen ander beheerdersaccount: de bestaande DPAPI-aanmelding
   hoort bij je huidige account.
2. Download [het Windows-updatepakket](../downloads/LCP-deursensor-update.zip)
   en kies in Verkenner **Alles uitpakken**. Pak het uit in Downloads, buiten
   `%LOCALAPPDATA%\LCP\Werklaptop`.
3. Dubbelklik op **Update-LCP-Deursensoren.cmd** in de uitgepakte map.
4. Wacht op **Update voltooid: MQTT verbonden en de vier deursensoren geladen**.
   De LCP-worker wordt kort herstart. De update maakt eerst een gecontroleerde
   back-up onder `%LOCALAPPDATA%\LCP\Werklaptop\worker-backups`.
5. Druk op de bestaande LCP-knop. Controleer dat je gewone iPhone-melding met
   de bestaande knoptekst aankomt.
6. Beweeg elke actieve deur eenmaal en sluit hem weer om de actuele
   uitgangsstatus te bevestigen. Open en sluit daarna nogmaals: controleer beide
   meldingen. Laat iedere nooddeur vijf minuten open om de extra waarschuwing
   te controleren. Sluiten binnen vijf minuten annuleert de waarschuwing.

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

Als de nieuwe worker niet goed start, zet de update de vorige worker en
runtime-instellingen terug en start zij de bestaande taak opnieuw. Voor handmatig
herstel kun je **Herstel-LCP-Worker.cmd** uit hetzelfde uitgepakte pakket openen.
Dit zet de laatste gecontroleerde workerback-up terug. Test daarna de bestaande
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
