# wann sehen wir uns wieder? · Fan-Kit

Ein Freund von mir, **Laurin.**, hat am 10. September 2026 sein erstes Lied veröffentlicht:
[„wann sehen wir uns wieder?“ auf Spotify](https://open.spotify.com/track/0yYpnpuC1tMqjxgXjMV0Vj).

Diese Seite ist ein Fan-Kit: **https://jul352mf.github.io/laurin-fan-kit/**
Sie zeigt, was ein Fan in fünf Minuten tun kann, damit ein erstes Lied wirklich gehört wird.
Alles darauf ist echt und erlaubt. Nichts davon ist ein Trick.

## Was ein Fan tut

1. **Hören**, am besten ganz.
2. **Speichern** und in eine eigene Playlist legen. Das zählt am meisten.
3. **Folgen**, damit das nächste Lied automatisch ankommt.
4. **Weitersagen** an eine Person, die es mögen wird.
5. Wenn es ein Video oder einen Shop gibt: anschauen, kommentieren, kaufen.

## Was nicht hilft

Das Lied stumm in Dauerschleife laufen lassen, Bots, Scripts, gekaufte Streams.
Spotify erkennt so etwas, streicht die Streams und kann im schlimmsten Fall das Lied sperren.
Das trifft den Künstler, nicht den Fan. Spotify for Artists sagt es selbst:
[artists.spotify.com/artificial-streaming](https://artists.spotify.com/artificial-streaming).

## Mitmachen

- Links zu Apple Music, YouTube, Bandcamp, SoundCloud, Instagram fehlen noch. Sobald sie da sind, kommen sie in `config.json`. Pull Requests sind willkommen.
- Ein Stern auf diesem Repo ist das Fan-Board: „ich bin dabei“.
- Wer die Seite für einen anderen Künstler nachbauen will: Fork, `config.json` und `assets/cover.jpg` tauschen, Texte anpassen.

## Zahlen

`stats.html` zeigt öffentliche Zahlen im Verlauf. Ein GitHub-Actions-Workflow (`.github/workflows/sample.yml`)
läuft täglich um 06:00 UTC, sammelt sie mit `tools/fanops` und schreibt sie nach `data/samples.jsonl`:

- monatliche Hörer von Laurins Spotify-Künstlerseite (öffentliches Meta-Tag)
- Sterne auf diesem Repo
- YouTube-Aufrufe, Likes und Kommentare, sobald `links.youtube_video_id` gesetzt ist (braucht das Secret `YOUTUBE_API_KEY`)

Spotify gibt kleinen Apps seit Februar 2026 keine Popularitäts- oder Follower-Zahlen mehr heraus,
deshalb kommt hier kein Spotify-Developer-Zugang zum Einsatz.

Tests: `uv run --directory tools/fanops --group dev pytest`

## Lizenz

MIT. Gebaut von Jules. Keine offizielle Seite von Laurin.
