# Memento Booth — Surface Pro Setup Guide

## Step 1: Install Node.js

1. Go to **nodejs.org** in Edge
2. Download the **LTS** installer (.msi)
3. Run it, click through with defaults
4. Open Command Prompt and verify: `node --version`

## Step 2: Clone the repo

```
git clone https://github.com/nymemento/photobooth.git
cd photobooth\booth-app
npm install
```

If Git isn't installed, download it from **git-scm.com** first.

## Step 3: Build the Windows app

```
npm run pack
```

This creates the installer at:
```
photobooth\booth-app\dist\Memento Booth Setup 1.0.0.exe
```

Run the installer. It auto-installs and launches.

## Step 4: Set up the Canon R100

1. On the camera: **Menu > Communication > USB connection mode > UVC/UAC**
2. Plug the Canon into the Surface Pro via USB-C
3. Open the Windows **Camera** app to confirm the feed shows up
4. Close the Camera app (only one app can use the camera at a time)

## Step 5: Set up the DNP DS RX1 printer

1. Plug the printer into the Surface Pro via USB
2. Download the driver from **dnpphoto.com/support** > DS-RX1
3. Install the driver
4. Open **Settings > Printers & Scanners**, confirm "DNP DS-RX1" appears
5. Right-click it > **Set as default printer**
6. Load **4x6" media** in the printer

The app prints a 4x6" sheet with two strips side by side. Cut down the middle to get two 2x6" strips.

## Step 6: Test the full flow

1. Launch Memento Booth (it should already be running from the installer)
2. Scan the QR code with your phone
3. Buy a print on the order page
4. Tap the start screen on the Surface Pro
5. Take 4 photos
6. Confirm it prints

## Step 7: Set up auto-start + watchdog

1. Press **Win+R**, type `shell:startup`, press Enter
2. Copy `photobooth\booth-app\scripts\watchdog.bat` into that folder
3. Edit `watchdog.bat` — update the `APP_PATH` line to point to the installed app:
   ```
   set APP_PATH=C:\Users\<your-username>\AppData\Local\Programs\Memento Booth\Memento Booth.exe
   ```
4. The watchdog will now auto-launch on boot and restart the app if it ever crashes

## Step 8: Kiosk hardening (optional)

- **Hide taskbar:** Right-click taskbar > Taskbar settings > "Automatically hide the taskbar" > On
- **Disable edge swipes:** Settings > Bluetooth & devices > Touch > Uncheck gesture options
- **Disable notifications:** Settings > System > Notifications > Off

## To exit kiosk mode

Tap the **top-right corner 5 times** within 3 seconds. The app will quit cleanly.

## Quick checklist before going live

- [ ] Canon R100 in UVC/UAC mode, connected via USB
- [ ] DNP printer set as default, media loaded
- [ ] Memento Booth app running fullscreen
- [ ] QR code scans and reaches the order page
- [ ] Test payment > photos > print works end to end
- [ ] Watchdog in startup folder
- [ ] Taskbar hidden
- [ ] Internet connection stable

## Troubleshooting

- **Camera not detected:** Unplug/replug Canon USB. Ensure UVC mode is set on the camera.
- **Prints not coming out:** Check printer has media and ribbon. Open Printers & Scanners to check status.
- **App frozen:** The watchdog should auto-restart. If not, Ctrl+Shift+Esc > End "Memento Booth" task.
- **No QR code showing:** Check internet connection. Server must be reachable.
- **Blank screen after launch:** Check Command Prompt for errors. Try `npm run dev` in the booth-app folder to test in dev mode first.
