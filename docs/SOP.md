# VideoFactory operator guide

Start the console with `python factory/app.py`. Follow [SETUP.md](SETUP.md) for the environment, FFmpeg, fonts, and speech provider. Faculty using a finished pack can print [SOP-faculty.html](SOP-faculty.html).

## Produce one lesson

1. **Choose the lesson and the cuts.** The standard matched cuts are English (`en`), Putonghua (`zh`), and Cantonese (`hk`) where the lesson has those tracks. A cut such as `en+zh` uses English narration and captions with bilingual slides. Select **Use existing narration audio** to use vendor MP3s.
2. **Run preflight.** Check the lesson, available cuts, fonts, FFmpeg, and any required local audio. Follow the lesson, language, and beat named in the report. For Google TTS, preflight checks local credentials. The build itself tests service availability.
3. **Preview slides and captions.** Review the business question, worked example, graphic reveals, units, glossary, and caption wrapping. Use [the lesson checklist](QA_CHECKLIST.md) for the language, evidence, and assessment review.
4. **Build the selected videos.** TTS prepares the narration tracks for a shared beat timeline. Use **Regenerate narration** when deliberately replacing existing TTS clips. Supply all complete local narration tracks if separately rendered vendor-audio cuts must align.
5. **Review the build report.** Open it in the console or find it in the output root under `reports/`. Each run has its own JSON file with the selected settings, source checksum, elapsed time by phase, warnings, and verified artifacts. Review the outputs marked **built** or **reused**. If a later cut fails, the completed cuts are still listed. Fix the reported problem before rebuilding the failed work.

## Verify the teaching outputs

- Play each cut you intend to publish. Confirm the language, readability, narration, captions, and final takeaway.
- Check that matched cuts share beat timing. A configured pad cap can intentionally shorten some cuts.
- Export and check the student quiz and answer key together. Each question should test the claim or decision taught in the lesson.
- Use the actual paths in the report. Standard lesson videos live under `lessons/<ID>/cells/` inside the output root. Preserve the stable lesson ID when moving reviewed files into the experiment library.

## Run from the command line

```sh
python factory/validate.py lessons/STAT/STAT-M01-T02-MEAN.yaml
python factory/build.py lessons/STAT/STAT-M01-T02-MEAN.yaml --preflight
python factory/build.py lessons/STAT/STAT-M01-T02-MEAN.yaml --caption-preview
python factory/build.py lessons/STAT/STAT-M01-T02-MEAN.yaml --cells en,zh,hk
```

Add `--no-tts` to preflight and to the build for vendor audio. Put MP3s under `lessons/<ID>/audio/<track>/<beat-id>.mp3` inside the output root. The tracks are `en`, `zh_cn`, and `zh_hk` for three-language lessons. Older two-language lessons use `zh` for Putonghua. The default output root is `Downloads/video-factory-out`. Use `--out` or `VF_OUT` to override it.

For batch or collection work, inspect the report per lesson before distributing files. Reviewers verify the teaching and language outputs, and operators verify the build and artifact records.

