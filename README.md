# Finnish Video Transcriber

Tama sovellus muuntaa videon tai aanitiedoston tekstiksi suomeksi kayttaen `faster-whisper`-kirjastoa.

## Ominaisuudet
- Auto-, CPU- ja GPU-kasittely yhdella valinnalla
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
- GPU-tilaa varten NVIDIA GPU ja `NVIDIA CUDA Toolkit 12.x`
- Testattu toimivaksi versiolla `CUDA Toolkit 12.4`
- Pelkka `CUDA 13.x` ei riita nykyisella `ctranslate2`-versiolla, koska se odottaa `CUDA 12` -kirjastoja

## Asennus

### Windows
1. Asenna Python.
2. Asenna ffmpeg ja varmista, etta `ffmpeg.exe` loytyy PATH:sta.
3. Jos haluat GPU-kiihdytyksen, asenna `NVIDIA CUDA Toolkit 12.x` (suositus: `12.4`).
4. Luo ja aktivoi virtuaaliymparisto:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```
5. Asenna riippuvuudet:
   ```bash
   pip install -r requirements.txt
   ```
6. Halutessasi lisaa paikallinen Whisper-malli esimerkiksi kansioon:
   ```text
   models\medium
   ```
7. Kaynnista:
   ```bash
   uvicorn app:app --reload
   ```
8. Avaa selaimessa:
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

## Ajotilat
- `Auto`: kayttaa GPU:ta, jos CUDA on saatavilla. Muuten kayttaa CPU:ta.
- `CPU`: pakottaa ajon prosessorille (`int8`)
- `GPU`: pakottaa ajon GPU:lle (`CUDA float16`)

Nykyinen `faster-whisper`-malli voidaan kaynnistaa GPU:lla ilman erillista muunnosta, kun CUDA on saatavilla.
`ffmpeg` tarvitaan edelleen aanen irrottamiseen videosta, mutta se ei vaikuta Whisperin GPU-kiihdytykseen.

## CUDA-huomio
- Nykyinen projekti kayttaa `ctranslate2`-wheelia, joka tarvitsee `CUDA 12.x` -ajonaikaiset kirjastot
- Jos koneessa on seka `CUDA 12.x` etta `CUDA 13.x`, projektin kannattaa kayttaa `CUDA 12.x` -polkua ensin
- Tarkista tarvittaessa:
  ```powershell
  where.exe cublas64_12.dll
  where.exe cublasLt64_12.dll
  where.exe cudart64_12.dll
  ```
- Jos `CUDA 12.4` ja `CUDA 13.x` ovat molemmat asennettuna, varmista etta `CUDA 12.4` on `PATH`:ssa ennen `CUDA 13.x`:aa

## Tallennus
- Jos selain tukee File System Access API:a, valmis tiedosto voidaan tallentaa valittuun kansioon.
- Muuten tiedosto ladataan selaimen tavalliseen latauskansioon.
- Selain ei aina paljasta tarkkaa absoluuttista levyosoitetta turvallisuussyista.

## Huomioita pitkiin videoihin
- CPU:lla kasittely voi kestaa pitkaan.
- GPU voi nopeuttaa kasittelya merkittavasti, jos CUDA on kaytettavissa.
- `medium` on hyva oletus useimpiin tilanteisiin.
- Sovellus irrottaa ensin aanen WAV-muotoon, joten valiaikaisesti tarvitaan lisaa levytilaa.
