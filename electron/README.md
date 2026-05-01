# SmartRehab Desktop (Electron)

Smart Rehabilitation Assessment System as a native desktop application.

## Prerequisites

- Node.js >= 18
- npm >= 9
- Python 3.10+ with all requirements from `requirements.txt` installed

## Development

```bash
cd electron
npm install
npm start
```

The app will:
1. Launch a Python subprocess running `streamlit run app.py --server.port 8502`
2. Wait up to 30 seconds for the Streamlit server to become available
3. Open a BrowserWindow displaying the Streamlit app

## Building Distributions

### Windows (NSIS Installer)
```bash
npm run build-win
```
Output: `electron/dist/SmartRehab Setup *.exe`

### macOS (DMG)
```bash
npm run build-mac
```
Output: `electron/dist/SmartRehab-*.dmg`

### Linux (AppImage)
```bash
npm run build-linux
```
Output: `electron/dist/SmartRehab-*.AppImage`

## Configuration

The Electron app uses port 8502 by default (must match `.streamlit/config.toml`).

App dimensions: 1400×900 (min 900×700), no menu bar, full-screen capable.

## Icon Setup

For builds, place these files in `electron/assets/`:
- `icon.png` (256×256 or larger PNG)
- `icon.ico` (Windows ICO format)
- `icon.icns` (macOS ICNS format)

## Notes

- The app bundles the entire project root via `extraResources` in `package.json`
- Logs appear in the console when running via `npm start`
- External links (http:/https:/file:/ftp:) open in the system browser
- Streamlit process is cleaned up on app exit
