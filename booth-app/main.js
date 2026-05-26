const { app, BrowserWindow, ipcMain, globalShortcut, session } = require("electron");
const path = require("path");
const fs = require("fs");
const { execFile } = require("child_process");

let mainWindow;

const isDev = !app.isPackaged;

app.commandLine.appendSwitch("disable-features", "MediaFoundationVideoCapture");
app.commandLine.appendSwitch("disable-video-capture-use-gpu-memory-buffer");
app.commandLine.appendSwitch("enable-media-stream");

function setupAutoStart() {
  if (isDev || process.platform !== "win32") return;
  app.setLoginItemSettings({
    openAtLogin: true,
    path: process.execPath,
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    fullscreen: !isDev,
    kiosk: !isDev,
    frame: isDev,
    width: 1080,
    height: 1920,
    alwaysOnTop: !isDev,
    skipTaskbar: !isDev,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (isDev) {
    mainWindow.loadURL("http://localhost:5173");
  } else {
    mainWindow.loadFile(path.join(__dirname, "dist", "index.html"));
  }

  mainWindow.webContents.on("context-menu", (e) => e.preventDefault());

  if (!isDev) {
    mainWindow.on("close", (e) => {
      e.preventDefault();
    });

    mainWindow.webContents.on("before-input-event", (_e, input) => {
      const blocked =
        (input.alt && input.key === "F4") ||
        (input.alt && input.key === "Tab") ||
        (input.meta && input.key === "d") ||
        input.key === "F11";
      if (blocked) _e.preventDefault();
    });

    mainWindow.webContents.on("did-fail-load", () => {
      setTimeout(() => {
        mainWindow.loadFile(path.join(__dirname, "dist", "index.html"));
      }, 3000);
    });

    mainWindow.webContents.on("render-process-gone", () => {
      mainWindow.webContents.reload();
    });

    mainWindow.webContents.on("unresponsive", () => {
      mainWindow.webContents.reload();
    });
  }

  session.defaultSession.setPermissionRequestHandler((_webContents, permission, callback) => {
    if (permission === "media") {
      callback(true);
      return;
    }
    callback(false);
  });

  session.defaultSession.setPermissionCheckHandler((_webContents, permission) => {
    if (permission === "media") return true;
    return false;
  });

  if (isDev) {
    mainWindow.webContents.openDevTools({ mode: "detach" });
  }
}

const outputDir = path.join(app.getPath("userData"), "photos");

function cleanupOldPhotos() {
  const maxAge = 7 * 24 * 60 * 60 * 1000;
  try {
    const files = fs.readdirSync(outputDir);
    const now = Date.now();
    let removed = 0;
    for (const file of files) {
      const filePath = path.join(outputDir, file);
      const stat = fs.statSync(filePath);
      if (now - stat.mtimeMs > maxAge) {
        fs.unlinkSync(filePath);
        removed++;
      }
    }
    if (removed > 0) console.log(`Cleaned up ${removed} old photo files`);
  } catch (err) {
    console.error("Photo cleanup error:", err);
  }
}

app.whenReady().then(() => {
  fs.mkdirSync(outputDir, { recursive: true });
  cleanupOldPhotos();
  setupAutoStart();
  createWindow();

  if (!isDev) {
    globalShortcut.register("Alt+F4", () => {});
    globalShortcut.register("Alt+Tab", () => {});
    globalShortcut.register("Super+D", () => {});
    globalShortcut.register("Super+E", () => {});
    globalShortcut.register("Super+R", () => {});
    globalShortcut.register("Ctrl+Alt+Delete", () => {});
  }
});

app.on("window-all-closed", () => {
  if (isDev && process.platform !== "darwin") app.quit();
});

ipcMain.handle("create-strip", async (_event, photosBase64) => {
  const sharp = require("sharp");

  const stripWidth = 600;
  const stripHeight = 1800;
  const photoHeight = 400;
  const photoTops = [25, 475, 925, 1375];

  const composite = [];

  for (let i = 0; i < photosBase64.length; i++) {
    const buf = Buffer.from(photosBase64[i].replace(/^data:image\/\w+;base64,/, ""), "base64");
    const resized = await sharp(buf)
      .resize(stripWidth, photoHeight, { fit: "cover" })
      .greyscale()
      .gamma(1.2)
      .linear(1.35, 8)
      .modulate({ brightness: 0.91 })
      .toColourspace("srgb")
      .recomb([
        [1.05, 0.0, 0.0],
        [0.0, 0.95, 0.0],
        [0.0, 0.0, 0.82],
      ])
      .toBuffer();
    composite.push({ input: resized, top: photoTops[i], left: 0 });
  }

  // Try multiple overlay paths: extraResources (unpacked), then ASAR (read via fs.readFileSync)
  const overlayPaths = [
    path.join(process.resourcesPath, "assets", "overlay.png"),
    path.join(__dirname, "assets", "overlay.png"),
  ];
  for (const overlayPath of overlayPaths) {
    try {
      if (fs.existsSync(overlayPath)) {
        // Read via Node's fs (ASAR-aware) then pass buffer to Sharp
        const overlayBuf = fs.readFileSync(overlayPath);
        const overlay = await sharp(overlayBuf)
          .resize(stripWidth, stripHeight)
          .toBuffer();
        composite.push({ input: overlay, top: 0, left: 0 });
        break;
      }
    } catch (err) {
      console.error(`Overlay load failed from ${overlayPath}:`, err);
    }
  }

  const stripBuffer = await sharp({
    create: {
      width: stripWidth,
      height: stripHeight,
      channels: 3,
      background: { r: 245, g: 240, b: 235 },
    },
  })
    .composite(composite)
    .jpeg({ quality: 95 })
    .toBuffer();

  const timestamp = Date.now();
  const stripPath = path.join(outputDir, `strip_${timestamp}.jpg`);
  fs.writeFileSync(stripPath, stripBuffer);

  const printSheetWidth = 1200;
  const printSheetHeight = 1800;
  const sheetBuffer = await sharp({
    create: {
      width: printSheetWidth,
      height: printSheetHeight,
      channels: 3,
      background: { r: 255, g: 255, b: 255 },
    },
  })
    .composite([
      { input: stripBuffer, top: 0, left: 0 },
      { input: stripBuffer, top: 0, left: 600 },
    ])
    .jpeg({ quality: 95 })
    .toBuffer();

  const sheetPath = path.join(outputDir, `sheet_${timestamp}.jpg`);
  fs.writeFileSync(sheetPath, sheetBuffer);

  return {
    stripBase64: "data:image/jpeg;base64," + stripBuffer.toString("base64"),
    stripPath,
    sheetPath,
  };
});

ipcMain.handle("print-strip", async (_event, sheetPath) => {
  if (!fs.existsSync(sheetPath)) {
    console.error("Print file not found:", sheetPath);
    return { success: false, error: "Print file not found: " + sheetPath };
  }

  return new Promise((resolve) => {
    // Use a hidden BrowserWindow for silent printing (works with all printers)
    const printWin = new BrowserWindow({
      show: false,
      width: 1800,
      height: 1200,
      webPreferences: { contextIsolation: true },
    });

    const imageData = fs.readFileSync(sheetPath);
    const base64 = imageData.toString("base64");
    const html = `<html>
<head><style>
  @page { size: 6in 4in; margin: 0; }
  html, body { margin: 0; padding: 0; width: 6in; height: 4in; overflow: hidden; }
  img { width: 100%; height: 100%; object-fit: contain; display: block; }
</style></head>
<body><img src="data:image/jpeg;base64,${base64}"></body>
</html>`;

    printWin.loadURL("data:text/html;charset=utf-8," + encodeURIComponent(html));

    printWin.webContents.on("did-finish-load", () => {
      printWin.webContents.print({
        silent: true,
        printBackground: true,
        landscape: true,
        margins: { marginType: "none" },
        pageSize: { width: 152400, height: 101600 },
      }, (success, failureReason) => {
        if (!success) {
          console.error("Silent print failed:", failureReason);
          // Fallback to PowerShell
          if (process.platform === "win32") {
            const psCmd = `Start-Process -FilePath "${sheetPath}" -Verb Print -WindowStyle Hidden`;
            execFile("powershell", ["-NoProfile", "-Command", psCmd], { timeout: 30000 }, (err) => {
              printWin.destroy();
              if (err) {
                console.error("PowerShell print also failed:", err);
                resolve({ success: false, error: failureReason });
              } else {
                resolve({ success: true });
              }
            });
          } else {
            printWin.destroy();
            resolve({ success: false, error: failureReason });
          }
        } else {
          console.log("Print sent successfully");
          printWin.destroy();
          resolve({ success: true });
        }
      });
    });

    // Safety timeout
    setTimeout(() => {
      if (!printWin.isDestroyed()) {
        printWin.destroy();
        resolve({ success: false, error: "Print timed out" });
      }
    }, 30000);
  });
});

ipcMain.handle("get-output-dir", () => outputDir);

ipcMain.handle("exit-kiosk", () => {
  if (mainWindow) {
    mainWindow.removeAllListeners("close");
    mainWindow.setKiosk(false);
    mainWindow.setAlwaysOnTop(false);
    mainWindow.setFullScreen(false);
  }
  globalShortcut.unregisterAll();
  app.quit();
});
