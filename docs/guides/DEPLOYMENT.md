docs/DEPLOYMENT.md: Installation guide for all platforms

## Installation

HearthNet is available as standalone executables, native packages, Docker containers, and source install. Choose the option that best fits your platform.

### 🪟 Windows

#### Option 1: Standalone EXE (recommended for beginners)
1. Download `HearthNet-Setup-Slim.exe` or `HearthNet-Setup-Full.exe`
2. Double-click to run installer
3. Choose installation directory (default: `C:\Program Files\HearthNet`)
4. Installer creates shortcuts on desktop and Start Menu
5. Launch HearthNet from Start Menu or double-click `HearthNet.lnk` on desktop

#### Option 2: Portable EXE (no installation)
1. Download `hearthnet-slim.exe` or `hearthnet-full.exe`
2. Run directly from any location
3. No system-wide installation required

#### First Run
- **Slim variant**: Prompts to select LLM backend (Ollama, llama.cpp, HF Transformers, or download SmolLM2)
- **Full variant**: Includes SmolLM2-135M model, runs immediately

#### Uninstall
- Use Windows Control Panel → Programs and Features → HearthNet → Uninstall
- Or delete the installation directory manually

---

### 🐧 Linux

#### Option 1: AppImage (recommended for all distros)
```bash
# Download HearthNet-x86_64.AppImage or HearthNet-aarch64.AppImage

# Make executable
chmod +x HearthNet-*.AppImage

# Run directly
./HearthNet-*.AppImage
```
- No installation needed
- Portable across all Linux distros
- Updates via downloading new AppImage

#### Option 2: Snap (Ubuntu/Linux with snapd)
```bash
# Install from Snap Store
sudo snap install hearthnet

# Run
hearthnet run

# Update
sudo snap refresh hearthnet
```

#### Option 3: Native Packages
**Ubuntu/Debian:**
```bash
sudo apt install ./hearthnet_0.1.0_amd64.deb
hearthnet run
```

**CentOS/RHEL/Fedora:**
```bash
sudo rpm -i hearthnet-0.1.0-1.x86_64.rpm
hearthnet run
```

#### First Run
- Automatically prompts for backend selection
- Model cached in `~/.cache/hearthnet/models/`

#### Uninstall
- Snap: `sudo snap remove hearthnet`
- deb: `sudo apt remove hearthnet`
- rpm: `sudo rpm -e hearthnet`
- AppImage: Delete the `.AppImage` file

---

### 🍎 macOS

#### Option 1: DMG Installer (recommended)
1. Download `HearthNet-Slim.dmg` or `HearthNet-Full.dmg`
2. Open the `.dmg` file (double-click)
3. Drag `HearthNet.app` to the Applications folder
4. Launch from Applications folder or Spotlight search

#### Option 2: Command Line
```bash
# If HearthNet.app is in Applications
/Applications/HearthNet.app/Contents/MacOS/hearthnet run

# Or via Spotlight
hearthnet run
```

#### First Run
- Slim variant: Configure LLM backend interactively
- Full variant: Ready to run with bundled model

#### Uninstall
- Drag `HearthNet.app` to Trash from Applications folder
- Or: `rm -rf /Applications/HearthNet.app`

---

### 🐳 Docker

#### Quick Start
```bash
# Slim (no bundled model)
docker run -p 7860:7860 ghcr.io/build-small-hackathon/hearthnet:0.1.0-slim

# Full (includes SmolLM2-135M)
docker run -p 7860:7860 ghcr.io/build-small-hackathon/hearthnet:0.1.0-full
```

Then open http://localhost:7860 in your browser.

#### Using Docker Compose (multi-node mesh)
```bash
git clone https://huggingface.co/spaces/build-small-hackathon/HearthNet
cd HearthNet
docker-compose -f build/docker/docker-compose.yml up -d
```

This starts:
- Alice node: http://localhost:7860
- Bob node: http://localhost:7861

They automatically discover each other via Docker network.

#### Persistence (keeping data between restarts)
```bash
docker run -p 7860:7860 \
  -v hearthnet-cache:/home/hearthnet/.cache \
  -v hearthnet-config:/home/hearthnet/.config \
  ghcr.io/build-small-hackathon/hearthnet:0.1.0-slim
```

#### Networking (accessing from other machines)
```bash
# Bind to all interfaces
docker run -p 0.0.0.0:7860:7860 \
  ghcr.io/build-small-hackathon/hearthnet:0.1.0-slim

# Now accessible at http://<machine-ip>:7860
```

---

### 📦 From Source

#### Requirements
- Python 3.12+
- pip
- git

#### Installation
```bash
# Clone repository
git clone https://huggingface.co/spaces/build-small-hackathon/HearthNet
cd HearthNet

# Create virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e .

# Run
python -m hearthnet.cli run
```

#### For development
```bash
pip install -r requirements-dev.txt
pytest tests/
```

---

## Configuration

### Selecting an LLM Backend

HearthNet supports multiple LLM backends. On first run, you'll be prompted to select:

1. **Ollama** (recommended for performance)
   - Install: https://ollama.ai
   - Run: `ollama serve`
   - HearthNet auto-detects and uses available models

2. **llama.cpp** (lightweight, CPU-only)
   - Install: https://github.com/ggerganov/llama.cpp
   - Excellent for Raspberry Pi or low-power devices

3. **HuggingFace Transformers** (local download)
   - HearthNet downloads model on first run (~500MB for SmolLM2-135M)
   - Requires PyTorch (GPU optional but recommended)

4. **OpenAI** (cloud, requires API key)
   - Set `OPENAI_API_KEY` environment variable
   - Only used if local backends unavailable
   - Note: Breaks local-first property; use only as fallback

### Configuration File

HearthNet stores configuration in:
- **Windows**: `%APPDATA%\HearthNet\config.json`
- **Linux/macOS**: `~/.config/hearthnet/config.json`

Edit to customize:
```json
{
  "llm_backend": "ollama",
  "model_id": "HuggingFaceTB/SmolLM2-135M-Instruct",
  "use_gpu": true,
  "max_tokens": 512
}
```

### Model Management

```bash
# Show current config
hearthnet config show

# Download a specific model
hearthnet model download HuggingFaceTB/SmolLM2-135M-Instruct

# Health check
hearthnet doctor
```

---

## Troubleshooting

### "Model not found" error
1. Run `hearthnet doctor` to check model availability
2. Run `hearthnet model download <model-id>` to download explicitly
3. Ensure `~/.cache/hearthnet/models/` has write permissions

### GPU not detected
1. Verify NVIDIA drivers: `nvidia-smi`
2. For Docker: Use `docker run --gpus all ...`
3. Check PyTorch installation: `python -c "import torch; print(torch.cuda.is_available())"`

### Port 7860 already in use
1. Find process: `lsof -i :7860` (Linux/macOS) or `netstat -ano | findstr :7860` (Windows)
2. Stop that process or specify different port: `hearthnet run --port 7861`

### Peer discovery not working
1. Ensure firewall allows UDP 5353 (mDNS) and TCP 8000 (P2P)
2. Run `hearthnet doctor` to diagnose connectivity
3. Check router doesn't block mDNS packets

### macOS "unverified developer" warning
1. Right-click app → Open → Allow
2. Or: `xattr -d com.apple.quarantine /Applications/HearthNet.app`

### Windows Defender warning
- SmartScreen may warn on first run
- Click "More info" → "Run anyway"
- Unsigned executables can be signed by the developer (future releases)

---

## Upgrading

### Windows
- Download new installer and run it
- Existing configuration preserved in `%APPDATA%\HearthNet\`

### Linux
- AppImage: Download and run new `.AppImage`
- Snap: `sudo snap refresh hearthnet`
- deb/rpm: Download and reinstall package

### macOS
- Download new `.dmg` and drag new app to Applications (replacing old one)

### Docker
```bash
# Pull latest image
docker pull ghcr.io/build-small-hackathon/hearthnet:latest-slim

# Stop old container
docker stop hearthnet

# Run new container
docker run -p 7860:7860 ghcr.io/build-small-hackathon/hearthnet:latest-slim
```

---

## Performance Tips

### GPU Acceleration
- Use NVIDIA GPU if available (10x faster inference)
- WSL2 on Windows supports NVIDIA CUDA
- Docker: `docker run --gpus all ...`

### Model Selection
- **Fast**: llama.cpp (CPU, low latency)
- **Balanced**: SmolLM2-135M (good quality, moderate speed)
- **Quality**: Larger models (Ollama supports up to 70B models)

### Multi-Node Mesh
- Run multiple nodes on same LAN for peer discovery
- Use relay servers for internet-wide mesh
- See [docs/HOWTO.md](https://github.com/build-small-hackathon/HearthNet/blob/main/docs/HOWTO.md) for advanced setup

---

## Getting Help

- **GitHub Issues**: https://github.com/build-small-hackathon/HearthNet/issues
- **Discussions**: https://github.com/build-small-hackathon/HearthNet/discussions
- **Documentation**: See [docs/](https://github.com/build-small-hackathon/HearthNet/blob/main/docs/)
- **Discord**: [Join community server]

---

**Last updated**: 2026-06-11
