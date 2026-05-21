const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("booth", {
  createStrip: (photosBase64) => ipcRenderer.invoke("create-strip", photosBase64),
  printStrip: (sheetPath) => ipcRenderer.invoke("print-strip", sheetPath),
  getOutputDir: () => ipcRenderer.invoke("get-output-dir"),
  exitKiosk: () => ipcRenderer.invoke("exit-kiosk"),
});
