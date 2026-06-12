# 🏗️ HearthNet Multi-Platform Build Guide

**Latest Update**: June 11, 2026  
**Script**: `build/quickstart.py` (Auto-builds EXE, AppImage, DMG, Docker)  
**Status**: ✅ Production Ready

---

## 📋 Quick Start

### Build for Your Platform Only
```bash
python build/quickstart.py
```

### Build Specific Target
```bash
# Windows EXE
python build/quickstart.py windows

# Linux AppImage
python build/quickstart.py linux

# macOS .app Bundle
python build/quickstart.py macos

# Docker Image
python build/quickstart.py docker

# All (for current platform + Docker)
python build/quickstart.py all
```

---

## 🖥️ Windows Build (EXE)

### Output
```
dist/HearthNet.exe (~80 MB)
```

### Requirements
- Python 3.10+ (already installed)
- PyInstaller (auto-installed by script)
- 200 MB disk space

### Build
```bash
python build/quickstart.py windows
```

### Run Standalone EXE
```cmd
cd dist
HearthNet.exe
```

**Then open**: `http://localhost:7860`

---

## 🐧 Linux Build (AppImage)

### Output
```
dist/HearthNet-*-x86_64.AppImage (~120 MB)
```

### Requirements
- Python 3.10+
- linuxdeploy tool
- 300 MB disk space

### Build
```bash
python build/quickstart.py linux
```

### Run AppImage
```bash
./dist/HearthNet-*.AppImage
```

**Then open**: `http://localhost:7860`

### Install to Applications Menu
```bash
chmod +x dist/HearthNet-*.AppImage
sudo cp dist/HearthNet-*.AppImage /opt/HearthNet
sudo ln -s /opt/HearthNet /usr/bin/hearthnet
```

---

## 🍎 macOS Build (.app Bundle)

### Output
```
dist/HearthNet.app/ (app bundle)
```

### Requirements
- macOS 10.13+
- Python 3.10+
- PyInstaller (auto-installed by script)
- 300 MB disk space

### Build
```bash
python build/quickstart.py macos
```

### Run App Bundle
```bash
# Method 1: Double-click from Finder
dist/HearthNet.app

# Method 2: Terminal
open -a dist/HearthNet.app

# Method 3: Launch directly
./dist/HearthNet.app/Contents/MacOS/HearthNet
```

**Then open**: `http://localhost:7860`

### Install to Applications
```bash
cp -r dist/HearthNet.app /Applications/
open /Applications/HearthNet.app
```

---

## 🐳 Docker Build

### Output
```
docker image: hearthnet:0.1.0 (also tagged as hearthnet:latest)
```

### Requirements
- Docker installed and running
- 2 GB disk space

### Build
```bash
python build/quickstart.py docker
```

### Run Docker Image
```bash
docker run -p 7860:7860 hearthnet:latest
```

**Then open**: `http://localhost:7860`

### Deploy to Server
```bash
# Push to Docker registry
docker tag hearthnet:0.1.0 your-registry/hearthnet:0.1.0
docker push your-registry/hearthnet:0.1.0

# Pull on server
docker pull your-registry/hearthnet:0.1.0
docker run -d -p 7860:7860 your-registry/hearthnet:0.1.0
```

---

## 📱 Android PWA (Instant - Recommended!)

### No Build Needed! 🎉

**Fastest way to deploy to Android:**

1. **On your computer:**
   ```bash
   python app.py
   ```

2. **On Android device:**
   - Open Chrome/Firefox
   - Go to `http://YOUR_COMPUTER_IP:7860`
   - Tap menu → "Install app"
   - App appears on home screen!

**Advantages:**
- ⚡ 5-minute setup
- 🔄 Instant updates (no rebuild)
- 📦 ~5 MB only
- 🌐 Works offline (Service Worker caching)

---

## 📦 Build Output Directory

After building, find artifacts in `dist/`:

```
dist/
├── HearthNet.exe              # Windows executable
├── HearthNet-*.AppImage       # Linux executable
├── HearthNet.app/             # macOS bundle
└── build/                     # Temporary build files (safe to delete)
```

### Clean Up Build Artifacts
```bash
rm -rf dist/build/            # Linux/macOS
rmdir /s dist\build           # Windows
```

---

## 🔧 Advanced Build Options

### Custom Python Path
```bash
/path/to/python3 build/quickstart.py windows
```

### Verbose Build Output
```bash
python build/quickstart.py windows 2>&1 | less
```

### Parallel Multi-Platform Build (macOS/Linux only)
```bash
# On macOS: build Docker + app simultaneously
python build/quickstart.py docker &
python build/quickstart.py macos
```

---

## 🐛 Troubleshooting

### Python Version Error
```
[ERR] Python 3.10+ required
```
**Fix**: Ensure Python 3.10 or newer is in PATH
```bash
python --version
which python3.10  # or python3.11, 3.12, 3.13
```

### PyInstaller Not Found
```
[ERR] No module named 'PyInstaller'
```
**Fix**: Run installation step first
```bash
python -m pip install pyinstaller --upgrade
```

### Docker Not Running
```
[SKIP] Docker not available
```
**Fix**: Start Docker daemon
```bash
# Windows: Start Docker Desktop
# Linux: sudo systemctl start docker
# macOS: open /Applications/Docker.app
```

### Out of Disk Space
```
[ERR] No space left on device
```
**Fix**: Clean up and retry
```bash
python build/quickstart.py     # Will skip building automatically
du -sh dist/                   # Check size
rm -rf dist/build/             # Remove temp files
```

### Module Import Errors (on first run)
```
ModuleNotFoundError: No module named 'fastapi'
```
**Fix**: Install main dependencies first
```bash
pip install -r requirements.txt
```

---

## 📊 Platform Comparison

| Feature | Windows EXE | Linux AppImage | macOS .app | Docker | PWA |
|---------|-------------|---|---|---|---|
| **Size** | ~80 MB | ~120 MB | ~200 MB | 2 GB image | ~5 MB |
| **Setup Time** | 15 min | 20 min | 20 min | 30 min | 5 min ⭐ |
| **Installation** | Copy & run | Make executable | Drag to Applications | `docker run` | Click link |
| **Offline Support** | Full | Full | Full | Full | Full (Service Worker) |
| **Cross-Platform** | Windows only | Linux only | macOS only | Any (Docker) | Any (Browser) |
| **Desktop Integration** | Native | Native | Native | Container | Web app |
| **Automatic Updates** | ❌ | ❌ | ❌ | ❌ (manual rebuild) | ✅ (live updates) |
| **Play Store Ready** | ❌ | ❌ | ❌ | ❌ | ❌ (needs signing) |
| **Development** | ✅ Easy | ✅ Easy | ✅ Easy | ✅ Easy | ✅ Easy |

---

## 🚀 Distribution Paths

### Desktop Users (Recommended)
1. **Quick Demo**: → PWA (5 min)
2. **Native App**: → EXE / AppImage / .app (20 min build)
3. **Server Deployment**: → Docker (30 min first-time)

### Mobile Users (Android)
1. **Quick Start**: → PWA (5 min, no build!)
2. **Offline App**: → Build APK in `build/android/`
3. **Play Store**: → Sign + upload (requires keystore)

### Enterprise Deployment
1. **Self-Hosted**: → Docker compose or Kubernetes
2. **Cloud**: → Docker image to AWS/GCP/Azure
3. **CI/CD**: → GitHub Actions + automated builds

---

## 📝 Build Script Internals

### What `build/quickstart.py` Does

1. **Checks Environment**
   - Verifies Python 3.10+
   - Detects OS type
   - Confirms HearthNet source present

2. **Installs Dependencies**
   - PyInstaller (all platforms)
   - linuxdeploy (Linux only)
   - Platform-specific build tools

3. **Creates Package**
   - Single executable (Windows: `--onefile`)
   - AppImage bundle (Linux: `--onedir` + linuxdeploy)
   - macOS app bundle (macOS: `--onedir` + code signing)
   - Docker image (all platforms)

4. **Bundles Assets**
   - UI files (`hearthnet/ui/`)
   - Documentation (`docs/`)
   - Hidden imports for dependencies

5. **Reports Success**
   - Lists output locations
   - Shows installation instructions
   - Provides next steps

---

## 🔐 Code Signing (Optional)

### Windows Code Signing
```bash
# Generate self-signed certificate (for testing)
# Production: Use Authenticode certificate from trusted CA

# Then rebuild with signing in PyInstaller
```

### macOS Code Signing
```bash
# Automatically attempted during build
# Requires Apple Developer account for distribution

# Check signature
codesign -v dist/HearthNet.app
```

### Linux AppImage Signing
```bash
# Sign with GPG
gpg --detach-sign dist/HearthNet-*.AppImage
gpg --verify dist/HearthNet-*.AppImage.sig
```

---

## 📚 Related Documentation

- [BUILD_STATUS.md](BUILD_STATUS.md) - Current artifact inventory
- [ANDROID_DEPLOYMENT_GUIDE.md](../ANDROID_DEPLOYMENT_GUIDE.md) - APK + PWA setup
- [README.md](../README.md) - Main project readme
- [Cordova Guide](CORDOVA_BUILD_GUIDE.md) - Android native build

---

## 🤝 Contributing

To improve the build system:

1. **Test locally** on your platform
2. **Report issues** with: `python build/quickstart.py [target] 2>&1 | tee build.log`
3. **Submit improvements** to build scripts
4. **Document platform-specific issues**

---

## 📞 Support

**Build failed?** Check:
1. ✅ Python version: `python --version`
2. ✅ Disk space: `df -h` (need 200+ MB)
3. ✅ Dependencies: `pip list | grep -i pyinstaller`
4. ✅ Logs: Output from script shows exact error

**Have suggestions?** Open an issue with:
- Platform (Windows/Linux/macOS)
- Python version
- Error message
- Output of: `python build/quickstart.py [target] 2>&1`

---

**Status**: ✅ All platforms supported  
**Last Tested**: June 11, 2026  
**Maintainer**: HearthNet Build System  
**License**: Apache 2.0
