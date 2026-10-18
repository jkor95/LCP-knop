# LCP Knop - proefversie 1.0

Voor de huidige instellingen voor titel, apparaatteksten, logo en persoonlijke testmeldingen: zie [Pushmeldingen beheren](docs/pushmeldingen.md). De bestaande Windows-/Zigbee-koppeling blijft behouden.

Een losse LCP-oproep-app om zonder hardware te testen of een iPhone-melding aankomt en of een lopend Windows-programma kan doorwerken terwijl de laptop vergrendeld is.

## Eerste GitHub-upload

1. Ga op GitHub naar **New repository**.
2. Repository name: **LCP-knop** (met streepje; GitHub-webadres bevat geen spaties).
3. Description: `LCP oproepsysteem - proefversie zonder hardware`.
4. Visibility: **Public** (voor GitHub Pages met een gratis persoonlijk account). Er komen geen codes of wachtwoorden in deze repository.
5. Zet **Add a README file** uit, zodat de eerste upload direct kan.
6. Klik **Create repository**.
7. Kies **uploading an existing file** en upload de bestanden `index.html`, `README.md` en `.nojekyll` uit dit pakket. Klik **Commit changes** op `main`.
8. Ga naar **Settings > Pages**. Kies **Source: Deploy from a branch**, **Branch: main**, **Folder: /(root)**. Klik **Save**.
9. Jouw webapp verschijnt na publicatie op `https://jkor95.github.io/LCP-knop/`.

Let op: de Windows `.cmd` die je later via de webpagina downloadt, bevat jouw persoonlijke topiccode. **Upload die niet naar GitHub.**

## Eerste iPhone-test

1. Open `https://jkor95.github.io/LCP-knop/` op je schoollaptop.
2. Klik **Genereer nieuwe code** (er verschijnt `lcp-` met 32 willekeurige hex-tekens).
3. Installeer de officiele **ntfy**-app uit de iOS App Store (zoek op `ntfy`).
4. Voeg in de ntfy-app een abonnement/topic toe met **exact dezelfde** code. Server: `https://ntfy.sh`.
5. Geef de ntfy-app toestemming om pushmeldingen te sturen. Zet op de iPhone eventueel Focus/Niet storen uit voor de test.
6. Klik **MEDEWERKER OPROEPEN** op de website. Controleer de melding op je iPhone. De website meldt alleen een verzendpoging: test daadwerkelijk de ontvangst.
7. Probeer daarna `F8` of `Spatie` terwijl de webpagina op de voorgrond staat. Toetsen werken niet op het Windows-vergrendelscherm.

## Windows-vergrendelingstest

1. Klik op de website **Download Windows-testprogramma**. Daardoor wordt een `LCP-Windows-Test.cmd` met dezelfde persoonlijke code gegenereerd.
2. Bewaar dit bestand **alleen lokaal** op de schoollaptop. Zet het niet op GitHub of in een gedeelde map.
3. Dubbelklik op `LCP-Windows-Test.cmd`. Windows kan een waarschuwing geven voor gedownloade scripts. Voer het niet uit als het ICT-beleid dit verbiedt; vraag dan toestemming.
4. Kies `1` om meteen een oproep te sturen. Dit controleert internettoegang voor `curl.exe` en `https://ntfy.sh`.
5. Kies `2` en druk meteen op **Windows + L**. Na 20 seconden verstuurt het reeds draaiende programma een testmelding.
6. Controleer of de iPhone de melding ontvangt terwijl de laptop vergrendeld is. Kom na het ontgrendelen terug in het opdrachtvenster om de melding `VERSTUURD` of een eventuele fout te zien.
7. Kies `3` om de test te sluiten.

**Let op:** een echte toetsdruk op het Windows-vergrendelscherm kan deze demo niet afhandelen. Deze test simuleert een toekomstige fysieke knop op de achtergrond. Slaapstand, uitgeschakelde wifi of internetblokkade kunnen de test verhinderen.

## Wat er niet in deze test zit

- Nog geen Zigbee-apparaten, USB-knop of achtergrondservice.
- Nog geen pushmelding die door de eigen GitHub Pages-site wordt ontvangen; daarvoor gebruiken we de externe gratis ntfy-app.
- Nog geen beveiligde/server-authenticatie. `ntfy.sh` gebruikt publiek te benaderen topics, en geheimhouding berust op een zeer moeilijk te raden topicnaam.
- Geen persoonsgegevens, leerlingnamen of vertrouwelijke schoolinformatie in de meldingen.

## Beveiliging en beheer

- De persoonlijke topicnaam wordt met `crypto.getRandomValues` op het apparaat gegenereerd; alleen in `localStorage` van die browser bewaard.
- Het publiek gehoste `index.html` bevat geen oproepcode en geen credentials.
- De lokaal gedownloade `.cmd` bevat wel de code; bewaar deze vertrouwelijk.
- Een ntfy-topic zonder toegangscontrole is niet geschikt als permanent oproepsysteem met garanties. Later kan een eigen backend met authenticatie worden toegevoegd.
- De gratis externe dienst kan storingen of vertragingen hebben. Gebruik dit niet als noodvoorziening.
- Overleg met ICT over het gebruik van de externe dienst en het uitvoeren van Windows-scripts op schoolapparatuur.

## Latere hardware

Voor de uiteindelijke Zigbee-knop komen er afzonderlijke lokale softwarecomponenten en een Zigbee USB-coordinator bij. De GitHub Pages-website alleen kan USB/Zigbee-signalen niet rechtstreeks lezen als de computer vergrendeld is.

## Bijwerken via GitHub

Na het maken van de repository en deze eerste upload kan een gekoppelde GitHub-integratie nieuwe bestanden en updates naar `jkor95/LCP-knop` schrijven. Met Pages op `main` en `/(root)` wordt de website vervolgens automatisch opnieuw gepubliceerd. De lokale `.cmd` moet je na wijziging van je oproepcode opnieuw downloaden.
