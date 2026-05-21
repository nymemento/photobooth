# Memento Booth — Surface Pro Setup

## 1. Build the Windows installer

On a machine with Node.js installed:

```bash
cd booth-app
npm install
npm run pack
```

The installer will be in `booth-app/dist/Memento Booth Setup X.X.X.exe`.

Copy the installer to the Surface Pro via USB drive.

## 2. Install on Surface Pro

Run the installer. It will:
- Install to `C:\Users\<user>\AppData\Local\Programs\Memento Booth\`
- Register to auto-start on boot
- Launch the app

## 3. Canon R100 Setup

1. On the Canon R100, go to **Menu > Communication > USB connection mode**
2. Set to **UVC/UAC** (webcam mode)
3. Connect Canon to Surface Pro via USB-C cable
4. Windows should recognize it as a webcam automatically
5. Test: open Camera app on Windows and confirm you see the Canon feed

## 4. DNP DS RX1 Printer Setup

1. Download DNP DS-RX1 driver from dnpphoto.com/support
2. Install the driver
3. Connect printer via USB
4. Open **Settings > Printers & Scanners**, confirm "DNP DS-RX1" appears
5. Set as default printer: right-click > Set as default
6. Print a test page to confirm
7. Load 4x6" media in the printer

**Paper cutting:** The print sheet is 1200x1800px (4x6"). It contains two strips side-by-side. After printing, cut down the middle to get two 2x6" strips.

## 5. Kiosk Lockdown (optional extras)

The app handles most lockdown itself (blocks Alt+F4, Alt+Tab, always-on-top, etc). For extra security:

### Disable Windows key combos via Group Policy:
```
gpedit.msc > User Configuration > Administrative Templates > Start Menu and Taskbar
- "Remove and prevent access to Shut Down" > Enabled
```

### Hide taskbar:
Right-click taskbar > Taskbar settings > "Automatically hide the taskbar" > On

### Disable touch keyboard (if not needed):
Settings > Time & Language > Typing > Touch keyboard > Off

### Disable edge swipes:
Settings > Bluetooth & devices > Touch > Uncheck "Three-finger and four-finger touch gestures"

## 6. Watchdog (auto-restart)

If you want the app to auto-restart after a crash:

1. Copy `scripts/watchdog.bat` to the desktop
2. Press Win+R, type `shell:startup`, press Enter
3. Create a shortcut to `watchdog.bat` in the startup folder

This replaces the direct app auto-start — the watchdog will handle launching and restarting.

## 7. Exit Kiosk Mode

To exit the app during development/troubleshooting:

1. Connect a USB keyboard
2. Press **Ctrl+Shift+Q** three times quickly (emergency exit — not yet implemented)
3. Or: open Task Manager via Ctrl+Shift+Esc > End "Memento Booth" process

## Troubleshooting

- **Camera not detected:** Unplug/replug Canon USB. Ensure UVC mode is set.
- **Prints not coming out:** Check printer has media and ribbon. Open Printers & Scanners to check status.
- **App frozen on black screen:** The watchdog should auto-restart. If not, Ctrl+Shift+Esc > End task.
- **No QR code showing:** Check internet connection. Server must be reachable.
