# HearthNet Android Deployment Guide

## Quick Start: PWA (Progressive Web App) - RECOMMENDED ⭐

**Status**: ✅ Ready to use now - no APK build needed!

### Install HearthNet on Android (ANY device, no installation required):

1. **Start the HearthNet server** on your computer:
   ```bash
   cd c:\Users\Chris4K\Projekte\HearthNet
   python app.py
   ```
   
2. **Find your computer's IP address**:
   ```powershell
   ipconfig
   # Look for "IPv4 Address" under your network (e.g., 192.168.1.100)
   ```

3. **On your Android device**, open any browser (Chrome, Firefox, Edge, Samsung Internet):
   - Go to: `http://YOUR_COMPUTER_IP:7860`
   - Example: `http://192.168.1.100:7860`

4. **Install as app** (browser-specific):
   - **Chrome/Edge**: Menu → "Install app" or "Add to home screen"
   - **Firefox**: Menu → "Install" 
   - **Samsung Internet**: Menu → "Add to home screen"

5. **Done!** 🎉 HearthNet is now on your home screen with:
   - Full offline support (Service Worker caching)
   - Native app appearance (standalone mode)
   - All features available

---

## Alternative: Native APK Build (Advanced)

### Why PWA is better:
- ✅ Works instantly - no build needed
- ✅ Updates automatically
- ✅ Works on Chrome, Firefox, Edge, Samsung Internet
- ✅ Smaller downloads (only web assets)
- ✅ No app store needed

### APK Build Status:
- ⚠️ Requires complex local setup: Java 17 JDK, Gradle, Android SDK, cmdline-tools
- ⚠️ Build time: 5-15 minutes
- ⚠️ APK size: ~80-100 MB
- ✅ One-time setup, then works offline completely

### If you want native APK anyway:

**Option A: Android Studio GUI (Recommended)**
1. Install [Android Studio](https://developer.android.com/studio)
2. File → Open → `c:\Users\Chris4K\Projekte\HearthNet\build\android\HearthNetApp`
3. Build → Build Bundle(s) / APK(s) → Build APK(s)
4. Find APK in: `platforms/android/app/build/outputs/apk/debug/app-debug.apk`
5. Install on device: `adb install -r app-debug.apk`

**Option B: Docker (Container-based)**
1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop)
2. Run build container:
   ```bash
   cd c:\Users\Chris4K\Projekte\HearthNet\build\android
   docker build -f Dockerfile.build -t hearthnet-builder .
   docker run --rm -v $(pwd)\HearthNetApp:/project hearthnet-builder
   ```

**Option C: Manual CLI Build**
1. Install Java 17 JDK, Gradle, Android SDK cmdline-tools
2. Set `ANDROID_HOME` environment variable
3. Run: `npx cordova build android --release`
4. APK appears in: `platforms/android/app/build/outputs/apk/`

---

## Testing Checklist

### PWA Testing (5 minutes):
- [ ] Server running: `python app.py`
- [ ] Browser opens: `http://YOUR_IP:7860`
- [ ] Install option appears in menu
- [ ] App icon on home screen
- [ ] Offline mode works (disable WiFi, app still loads)
- [ ] Chat/Ask/Mesh features functional

### APK Testing (if building):
- [ ] APK file generated (~80 MB)
- [ ] Device has USB Debugging enabled
- [ ] ADB recognizes device: `adb devices`
- [ ] Install: `adb install -r app-debug.apk`
- [ ] Tap launcher icon to open
- [ ] Enter server IP and connect
- [ ] Same features work as PWA

---

## Features Available

Both PWA and APK include:
- ✅ Service Worker offline caching
- ✅ Local-first P2P mesh network
- ✅ Chat interface
- ✅ Ask (LLM) interface
- ✅ Mesh network topology view
- ✅ Landing page with server connection
- ✅ Persistent storage (localStorage)
- ✅ Background sync placeholder

---

## Troubleshooting

### "Cannot connect to server"
- Check computer is on same WiFi as Android device
- Verify server running: `python app.py`
- Try ping: `ping 192.168.1.100` from Android (some WiFis block)
- Check firewall isn't blocking port 7860

### PWA not installing
- Use Chrome/Edge/Firefox (Samsung Internet also works)
- Tap menu icon (⋮ or three dots)
- Look for "Install" or "Add to Home Screen"
- Not all browsers show this option

### APK won't install
- Enable developer mode: Settings → About Phone → tap Build# 7 times
- Enable USB Debugging: Settings → Developer Options → USB Debugging
- Try: `adb install -r app-debug.apk` (includes -r flag to replace)

### Build errors
- Run: `npx cordova clean` before rebuilding
- Remove: `platforms/android` folder and re-add platform
- Check Java: `java -version` returns 17+
- Check Android SDK: `android list targets` shows API 31+

---

## Architecture

```
User Browser/App
     ↓
  PWA/APK
     ↓
 Cordova Wrapper (APK only)
     ↓
FastAPI Backend (http://localhost:7860)
     ↓
  HearthNet Mesh
     ↓
  P2P Network
```

---

## Next Steps

1. **Try PWA first** (5 minutes):
   ```bash
   python app.py
   # Then open http://YOUR_IP:7860 on Android
   ```

2. **If you need native APK**:
   - Use Android Studio GUI (easiest)
   - Or follow Docker instructions
   - Or follow manual CLI instructions

3. **Deploy to Play Store** (future):
   - Sign APK with keystore
   - Create Google Play account
   - Upload and publish

---

## Documentation Files

- [PWA Implementation](docs/M08-ui.md) - Full web app details
- [Cordova Build Guide](build/android/CORDOVA_BUILD_GUIDE.md) - Detailed native build
- [APK Setup](build/android/SETUP_COMPLETE.md) - Project status
- [Build Paths](build/android/BUILD_PATHS.md) - Decision guide

---

**Recommended**: Start with PWA - it's production-ready now! 🚀
