# One Story, Three Frames

A portable composition lab for a fictional pad and signal display. The editor supports one structured JSON scene, two manual focal controls, two caption anchors and four PNG or two-second motion export sizes. It also reads version 1 static scenes. The deliberate center crop is a diagnostic view. It cuts a real slice of the wide canvas.

## Run the site

From this directory, start `python3 server.py` and open http://127.0.0.1:8765. A packaged copy includes the finished public downloads and animation. A fresh source checkout generates those assets with the commands below. Open the lab, choose a composition, move either slider with the keyboard, then choose **Render 2s clip** and **Play exported file**. Chromium WebM export uses MediaRecorder, with the available codec selected at runtime. PNG remains available in browsers without the required recording support.

## Local analytics

Set `FRAME_ADMIN_PASSWORD` in the server environment using a locally generated secret. The admin username is `admin`. The admin page is http://127.0.0.1:8765/admin. To generate a password in Bash without putting its value in shell history, use `export FRAME_ADMIN_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"`. Use the generated value from your private environment when signing in. The collector runs with the admin disabled when no secret is configured.

`FRAME_DB` selects the SQLite database path and defaults to `var/events.sqlite3` beside the server script. Put it on durable storage outside the static site. Events retain the UTC day, event name, fixed content/variant/campaign IDs and a test/standard traffic label. They do not include input text, IP address, account identifier, user agent or referrer. Append `?traffic=test` for a labeled test. Private `?capture` sessions suppress tracking.

To prepare an authorized deployment, place the server behind an HTTPS reverse proxy with basic request-size and rate limits, disable access logging or configure it for the same privacy scope, store the admin password in the host secret manager, mount a persistent volume for the database and restrict its file permissions. Use a service supervisor to restart the process, preserve the volume and exercise the restart and anonymous-admin checks below. The provided default bind is loopback. `--bind` and `--port` can be set for the chosen infrastructure. Review the draft canonical, absolute social-image URL and destination privacy settings at deployment. The site ships with noindex.

## Reproduce the package assets

The production scripts use Python 3, Pillow, Playwright for Python, Chromium and FFmpeg. These dependencies were provisioned in the production workspace. Python alone serves the finished package. In a fresh checkout, generate the guide before testing its download.

```sh
python3 production/guide.py
python3 server.py
```

With that server running, use another terminal in this directory. The fresh capture is a real browser session and will have new run timestamps and encoder metadata. For exact editing evidence use the saved capture supplied in the private package.

```sh
python3 production/verify.py build/tests
python3 production/capture.py build/capture
python3 production/film.py sample build/capture build/sample
python3 production/film.py full build/capture build/films
python3 production/loop.py site/animation
python3 production/platforms.py build/platforms
```

The sample command produces three frames and a 12-second proof excerpt. The film command generates 50-second clean and captioned MP4s, four-second hooks, covers, timed captions and transcript. It uses the recorded screenshot timestamps and the actual exported video files. The 30 fps delivery has a 12 fps sampled proof track. Each production script exposes `--help`. Live capture timings vary. If recapturing for another edit, align the proof/caption cues against the new `capture.json` and review that revision.

## Editable sources

- `site/scene.js` draws the pad, scope, cable, trace and text for each ratio. `site/default.json` and `fixtures/` are scene data.
- `production/guide.py` creates an editable SVG, PNG, PDF and checklist. SVG text is live. The offset copy and outline create the display lettering effect. PDF inspection may report a Type 3 font for the outlined stroke effect.
- `production/film.py` contains the edit decisions, cue timing, compositions and encoding settings. `production/loop.py` contains the four-second movement path. `site/embed.html` shows a static poster for reduced motion; `site/embed-snippet.html` is pasteable HTML.
- `production/platforms.py` generates six editable guide pages, JPEG versions, a six-page PDF and the channel copy.
- `site/fonts/sources.json` pins source revisions, font versions, URLs and SHA-256 digests. Knewave and Source Sans 3 are substitutes. Both fonts and their OFL licenses are bundled.

