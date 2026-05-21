const { app, BrowserWindow, ipcMain, globalShortcut } = require("electron");
const path = require("path");
const fs = require("fs");
const { execFile } = require("child_process");

let mainWindow;

const isDev = !app.isPackaged;

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
  const photoTops = [33, 490, 944, 1392];

  const composite = [];

  for (let i = 0; i < photosBase64.length; i++) {
    const buf = Buffer.from(photosBase64[i].replace(/^data:image\/\w+;base64,/, ""), "base64");
    const resized = await sharp(buf)
      .resize(stripWidth, photoHeight, { fit: "cover" })
      .greyscale()
      .normalize()
      .linear(2.05, -51)
      .modulate({ brightness: 0.82 })
      .gamma(1.05)
      .tint({ r: 216, g: 204, b: 189 })
      .toBuffer();
    composite.push({ input: resized, top: photoTops[i], left: 0 });
  }

  const overlayPath = path.join(__dirname, "assets", "overlay.png");
  if (fs.existsSync(overlayPath)) {
    const overlay = await sharp(overlayPath)
      .resize(stripWidth, stripHeight)
      .toBuffer();
    composite.push({ input: overlay, top: 0, left: 0 });
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
  return new Promise((resolve) => {
    if (process.platform === "win32") {
      execFile(
        "rundll32",
        ["shimgvw.dll,ImageView_PrintTo", `/pt`, sheetPath, ""],
        { timeout: 30000 },
        (err) => {
          if (err) {
            console.error("Print via shimgvw failed, trying fallback:", err);
            execFile(
              "mspaint",
              ["/p", sheetPath],
              { timeout: 30000 },
              (err2) => {
                if (err2) {
                  console.error("Print fallback failed:", err2);
                  resolve({ success: false, error: err2.message });
                } else {
                  resolve({ success: true });
                }
              }
            );
          } else {
            resolve({ success: true });
          }
        }
      );
    } else {
      execFile("lp", [sheetPath], (err) => {
        if (err) {
          console.error("Print error:", err);
          resolve({ success: false, error: err.message });
        } else {
          resolve({ success: true });
        }
      });
    }
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
