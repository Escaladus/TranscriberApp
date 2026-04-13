# Finnish Video Transcriber

Tämä sovellus muuntaa videon tai äänitiedoston tekstiksi suomeksi käyttäen `faster-whisper`-kirjastoa.

## Ominaisuudet
- Tukee pitkiä tiedostoja, myös noin 1.5 h videoita
- Drag & drop -käyttöliittymä selaimessa
- Suomen kieli (`language="fi"`)
- TXT- tai SRT-ulostulo
- Mahdollisuus ladata valmis tiedosto tai tallentaa se valittuun kansioon selaimen kautta

## Vaatimukset
- Python 3.10+
- `ffmpeg` asennettuna ja PATH:ssa
- Riittävästi levytilaa pitkän videon väliaikaisille tiedostoille

## Asennus

### Windows
1. Asenna Python.
2. Asenna ffmpeg ja varmista, että `ffmpeg.exe` löytyy PATH:sta.
3. Luo ja aktivoi virtuaaliympäristö:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```
4. Asenna riippuvuudet:
   ```bash
   pip install -r requirements.txt
   ```
5. Käynnistä:
   ```bash
   uvicorn app:app --reload
   ```
6. Avaa selaimessa:
   ```
   http://127.0.0.1:8000
   ```

## Huomioita 1.5 tunnin videoista
- CPU:lla käsittely voi kestää pitkään.
- `medium` on hyvä oletus. `large-v3` antaa usein paremman laadun, mutta on raskaampi.
- CUDA-GPU nopeuttaa paljon, jos käytettävissä.
- Sovellus irrottaa ensin äänen WAV-muotoon, joten väliaikaisesti tarvitaan lisää levytilaa.

## Mahdollisia jatkoparannuksia
- Taustajono pitkille töille
- Reaaliaikainen progress bar
- ZIP-paketti, jos halutaan sekä TXT että SRT samalla kertaa
- Puhujien erottelu (speaker diarization)
