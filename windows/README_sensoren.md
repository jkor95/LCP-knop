# LCP – sensoruitbreiding (oktober 2026)

Deze uitbreiding gebruikt dezelfde bestaande Windows 11-laptop, SONOFF ZBDongle-P, Mosquitto, Zigbee2MQTT, Supabase en DPAPI-inloggegevens. Bestaande Windows-taken blijven behouden.

## Ingebruikname

1. Open de LCP-webapp en meld je aan als beheerder. Klik **Sensoren en meldingen beheren** of open \`settings.html\`.
2. De bestaande knop \`LCP_knop\` staat aan met dezelfde oproeptekst als voorheen. De nieuwe \`LCP_deur\` staat uit.
3. Laat de bestaande achtergrondworker voorlopig draaien. Test de webapp-instellingen en sla ze op.
4. Download het bestand \`windows/installeer_lcp_sensoren.cmd\` via GitHub (Download raw) naar je Windows-laptop.
5. Controleer de inhoud en voer het als beheerder uit op een moment waarop een korte onderbreking van LCP acceptabel is. Het script maakt **eenmalig** de back-up \`C:\LCP\lcp_worker_voor_sensoren.py\`, downloadt de nieuwe worker, controleert Python-syntax, beëindigt alleen taak \`LCP - Achtergrondworker\`, vervangt \`C:\LCP\lcp_worker.py\` en start de taak weer.
6. Druk op de bestaande fysieke SONOFF-knop. Controleer dat de ingestelde pushtekst aankomt.
7. Koppel de Zigbee-contactsensor met Zigbee2MQTT. Geef deze bij voorkeur de Friendly name \`LCP_deur\`. Controleer in Zigbee2MQTT dat \`contact:true\` staat voor gesloten en \`contact:false\` voor open.
8. Activeer \`LCP_deur\` via de LCP-webapp. Kies automatische planning of handmatig AAN/UIT, stel eventueel de meldteksten en het aantal minuten in, en sla op.
9. Test een korte deurbeweging binnen een ingeschakeld beveiligingsmoment; test een langdurig geopende deur (bijvoorbeeld tijdelijk met 1 minuut).

## Huidig gedrag

- Knop: bericht bij een enkele druk, met anti-dubbelklikbeveiliging.
- Deur: directe melding **alleen** wanneer het beveiligingsschema of handmatig AAN actief is.
- Deur langer open: **onafhankelijk** van het beveiligingsschema, indien aangevinkt. De teller begint bij de waargenomen openingsstatus en wordt gewist zodra de sensor meldt dat de deur dicht is.
- In de lange-open-tekst kun je \`{minuten}\` gebruiken; dit wordt vervangen door het aantal ingestelde minuten.
- Beheerders mogen de instellingen beheren; overige geautoriseerde LCP-gebruikers kunnen hun bestaande meldingen blijven ontvangen.
- Laptop haalt instellingen ongeveer elke 15 seconden op. Een wijziging is dus niet onmiddellijk gegarandeerd.
- Deur is standaard **uitgeschakeld** totdat de echte sensor is gekoppeld.
- Het lokale sensorstatusbestand is \`C:\LCP\config-jeremy\sensor_state.json\`.
- Het automatische schema gebruikt de **lokale Windows-tijd**. Stel op de laptop de juiste Nederlandse tijdzone in.
- Pushmeldingen blijven afhankelijk van internet, Zigbee, de laptop en iOS-aflevering. Dit is geen gecertificeerd inbraakalarm.
- Tijdens laptopuitval worden sensorovergangen niet ontvangen. Een na herstart bewaarde openstatus kan daarom verouderd zijn; controleer na uitval de werkelijke deurstatus.

## Herstel oude worker

Open CMD als beheerder en voer uit:

\`\`\`cmd
schtasks /end /tn "LCP - Achtergrondworker"
copy /Y "C:\LCP\lcp_worker_voor_sensoren.py" "C:\LCP\lcp_worker.py"
schtasks /run /tn "LCP - Achtergrondworker"
\`\`\`

De overige installatie blijft ongewijzigd. Test daarna de bestaande knop.

## Opmerkingen

De webapp en Supabase-configuratie zijn online gepubliceerd. De upgrade van de Windows-worker gebeurt **niet op afstand** en vereist bovenstaande eenmalige uitvoering op de laptop. De originele GitHub-code \`windows/lcp_worker.py\` wordt niet vervangen. Windows DPAPI-inloggegevens en gebruikersaccounts hoeven niet opnieuw te worden ingericht.
