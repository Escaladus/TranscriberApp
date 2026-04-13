# Finnish Video Transcriber

Tama sovellus muuntaa videon tai aanitiedoston tekstiksi suomeksi kayttaen `faster-whisper`-kirjastoa.

## Ominaisuudet
- CPU-only kasittely yksinkertaisemmalla asetuksella
- Selainpohjainen kayttoliittyma drag & drop -tuella
- Suomen kieli (`language="fi"`)
- TXT- tai SRT-ulostulo
- Tallennus valittuun kansioon selaimen kautta, jos selain tukee sita
- Selkea ilmoitus, kun kasittely on valmis

## Vaatimukset
- Python 3.10+
- `ffmpeg` asennettuna ja PATH:ssa
- Riittavasti levytilaa valiaikaisille tiedostoille
- Whisper-malli saatavilla joko verkosta tai paikallisessa kansiossa `models/<malli>`

## Asennus

### Windows
1. Asenna Python.
2. Asenna ffmpeg ja varmista, etta `ffmpeg.exe` loytyy PATH:sta.
3. Luo ja aktivoi virtuaaliymparisto:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```
4. Asenna riippuvuudet:
   ```bash
   pip install -r requirements.txt
   ```
5. Halutessasi lisaa paikallinen Whisper-malli esimerkiksi kansioon:
   ```text
   models\medium
   ```
6. Kaynnista:
   ```bash
   uvicorn app:app --reload
   ```
7. Avaa selaimessa:
   ```text
   http://127.0.0.1:8000
   ```

Vaihtoehtoisesti voit kaynnistaa projektin ja avata selaimen automaattisesti:
```powershell
.\run.ps1
```

## Mallit
- `small`: kevyin ja nopein
- `medium`: suositeltu tasapaino laadun ja nopeuden valilla
- `large-v3`: tarkin, mutta raskain CPU:lla

Jos paikallinen malli loytyy polusta `models/<malli>`, sovellus kayttaa sita. Muuten `faster-whisper` yrittaa ladata mallin normaalisti.

## Tallennus
- Jos selain tukee File System Access API:a, valmis tiedosto voidaan tallentaa valittuun kansioon.
- Muuten tiedosto ladataan selaimen tavalliseen latauskansioon.
- Selain ei aina paljasta tarkkaa absoluuttista levyosoitetta turvallisuussyista.

## Huomioita pitkiin videoihin
- CPU:lla kasittely voi kestaa pitkaan.
- `medium` on hyva oletus useimpiin tilanteisiin.
- Sovellus irrottaa ensin aanen WAV-muotoon, joten valiaikaisesti tarvitaan lisaa levytilaa.
