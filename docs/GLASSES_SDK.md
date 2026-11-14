# Ray-Ban Meta Glasses: Context for the Hackathon

This is a summary of what we learned building **MetaGlass**, an Android app that helps blind and
low-vision users find, frame and understand data charts through Ray-Ban Meta glasses. You don't
need the chart features for the hackathon. The useful parts are how to get camera frames and
photos off the glasses, what breaks, and which pieces of our code you can reuse.

---

## 1. What the glasses can and can't do for a third-party app

- **SDK:** Meta's *Wearables Device Access Toolkit* (DAT), Android artifacts `mwdat-core`,
  `mwdat-camera`, `mwdat-mockdevice`, version **0.7.0**. Our app is built on Meta's
  "CameraAccess" sample, which is why the package name is
  `com.meta.wearable.dat.externalsampleapps.cameraaccess`.
- **What you get:** a live **video stream** (we use `VideoQuality.HIGH` at 30 fps) and
  **on-demand photos** (`capturePhoto()`, 1080×1440, about 1.3–2.1 s round trip).
- **What you don't get:** the glasses don't run your code. Everything (ML, API calls, TTS)
  happens on the **phone**. Audio goes back to the user through the phone's TTS, which plays in the
  glasses' speakers once they're paired as a Bluetooth audio device.
- **Everything goes through the Meta AI app.** The glasses have to be paired in the Meta AI app,
  and camera permission for your app is granted through it
  (`Wearables.RequestPermissionContract()`).

## 2. Setup checklist

1. **GitHub PAT** with `read:packages`. The SDK is served from GitHub Packages:
   `https://maven.pkg.github.com/facebook/meta-wearables-dat-android`.
   Put it in `local.properties` as `github_token=...` or export `GITHUB_TOKEN`.
2. **Android Studio / JDK 21** for the Gradle daemon. Our repo pins it; foojay downloads it
   automatically.
3. Versions: AGP 8.6.0, Kotlin 2.1.20, Compose, compileSdk 35, **minSdk 31**.
4. Manifest:
   - Permissions: `BLUETOOTH`, `BLUETOOTH_CONNECT`, `INTERNET`, `CAMERA`.
   - `<meta-data android:name="com.meta.wearable.mwdat.APPLICATION_ID" android:value="0"/>`.
     `0` works while **Developer Mode** is on in the Meta AI app. Otherwise you need an app ID
     from the Wearables Developer Center.
5. On the phone: Meta AI app installed, glasses paired, Developer Mode enabled.
6. Call `Wearables.initialize(context)` **only after** the Android runtime permissions are
   granted, then `Wearables.startRegistration(activity)`.

## 3. Minimal flow, from our code

```kotlin
// After permissions:
Wearables.initialize(this)
Wearables.startRegistration(activity)          // links your app via Meta AI app

// Observe devices
Wearables.devices.collect { ids -> /* pick one */ }

// Session → stream
val session = Wearables.createSession(selector).getOrNull() ?: return
session.start()                                  // wait for STARTED (we wait up to 5s)
val stream = session.addStream(StreamConfiguration(videoQuality = VideoQuality.HIGH, 30)).getOrNull()
stream.start()

stream.videoStream.conflate().collect { frame: VideoFrame -> /* YUV → Bitmap, run ML */ }
stream.errorStream.collect { err -> Log.e(TAG, "$err") }
stream.state.collect { st: StreamState -> /* STARTING / STREAMING / STOPPED ... */ }

// High-res still
stream.capturePhoto()   // returns PhotoData; we time out after 5s and fall back to a stream frame
```

Reference files (path root
`app/src/main/java/com/meta/wearable/dat/externalsampleapps/cameraaccess/`):

| File | Why look at it |
|---|---|
| `MainActivity.kt` | Permissions, `Wearables.initialize`, the Meta AI permission contract |
| `wearables/WearablesViewModel.kt` | Registration and device discovery, including the mock-device polling workaround |
| `stream/StreamViewModel.kt` (`startStream()` around line 330, `capturePhoto()` around line 600) | Session/stream lifecycle, frame handling, photo capture with timeout |
| `stream/YuvToBitmapConverter.kt`, `PresentationQueue.kt` | Fast YUV→Bitmap with pooled buffers |
| `alignment/AudioGuidanceEngine.kt` | TTS with "wait until narration is done" (`UtteranceProgressListener`) |
| `mockdevicekit/MockDeviceKitViewModel.kt` | Developing without glasses |

## 4. Developing without glasses: Mock DevKit

`mwdat-mockdevice` adds a fake paired device that streams either the **phone's rear camera** or a
**video file**, as if it came from the glasses. Videos must be HEVC; `tools/convert_to_hevc.sh`
converts them. Use this for most of the dev loop and save the real glasses for integration
testing, because only one person can use them at a time.

On the emulator, `Wearables.devices` may never emit for mock devices. That's why we also poll
`MockDeviceKit.getInstance(ctx).pairedDevices`.

## 5. Gotchas that cost us days

- **If the glasses misbehave, toggle the physical power switch off and on first.** Symptoms:
  the stream says STREAMING but delivers 0 frames, error 5106 "camera failure", no second
  power-on chime, native video recording broken. We lost a week (Oct 9–16) to this. It wasn't
  our code.
- **The stream runs over Bluetooth on Android, not Wi-Fi.** Bandwidth is about 450–500 kbps at
  about 28 fps. No app API forces Wi-Fi Direct. (The iOS SDK ≥ 0.8 has a Wi-Fi transport.)
- **`HIGH` is a ceiling, not a guarantee.** The SDK silently downscales to **504×896** when the
  BT link weakens. Check the frame dimensions you actually receive. If you need detail
  (reading text, small objects), use `capturePhoto()`.
- **Stream frames are soft and noisy**, especially in low light. Our pattern: use the stream to
  *find and aim*, then take a photo for the actual analysis.
- **Photo latency is about 1.3–2.1 s.** Tell the user to hold still. We retake once if the
  photo is blurry (Laplacian variance < 180).
- **Don't call `createSession()` twice.** A leaked session causes `SESSION_ALREADY_EXISTS`.
  Stop and clean up the old one first.
- **Don't recycle pooled bitmaps** that are still in use by a presentation queue. We got
  "Canvas: trying to use a recycled bitmap" and lag.
- **TTS interruptions:** guidance cues will cut off longer narration unless you track utterance
  completion.
- **Auto-reconnect loops are a trap.** We tried an automatic quality-fallback ladder, and it
  kept reconnecting to the glasses after the app was closed. Keep reconnects user-initiated.
- `String.format(Locale.ROOT, "%.2f", x)`, not `"%0.2f"`. The latter crashed.

## 6. Reusable building blocks from MetaGlass

- **On-device detection:** TFLite YOLOv8n (416 input) at about 115 ms per frame on a Pixel 6a.
  We run it on every 5th–10th frame on a background thread so the stream stays smooth. The
  training notebook is `ml_pipeline/train_chart_detector.ipynb` (Colab), and it can be adapted
  to other object classes.
- **Data collection mode** (`util/TrainingCollector.kt`): saves a frame every second plus photos,
  with draft YOLO labels. `scripts/review_labels.py` is a local label-review page that exports a
  YOLO train/val/test split. Useful if you need a custom detector quickly.
- **Vision-LLM fallback chain** (`alignment/VisualizationAnalysisService.kt`): OpenAI
  `gpt-4o-mini` → Gemini `gemini-2.5-flash` → on-device ML Kit OCR, returning structured JSON.
  API keys go in `local.properties` and are exposed as `BuildConfig.*`. Never commit them.
- **Audio-first UX for blind users:** directional cues ("Turn left a little", "Tilt up a lot",
  "Centered"), a cooldown after each capture, and spoken errors when the result isn't what was
  expected.
- **Diagnostics** (`util/DetectionDiagnosticLogger.kt`, `util/FileLogger.kt`): per-frame JSONL
  and thumbnails in debug builds. Pull them with `scripts/pull_diagnostics.sh`.

## 7. Hardware we tested on

Pixel 6a with real Ray-Ban Meta glasses, plus Mock DevKit on the same phone. Android only. An
iOS port plan is in `docs/IOS_PORT_PLAN.md` if the team uses iPhones.

## 8. Debugging commands

```bash
adb logcat -s StreamViewModel YoloChartDetector VisualizationAnalysis
adb logcat | grep "XMS:WARPStreamClientService"   # glasses link bitrate ("recv bitrate")
./gradlew :app:installDebug
```
