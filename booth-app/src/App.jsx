import { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";
import homeBg from "../assets/home-bg.png";
import countdownVideo from "../assets/countdown.mp4";
import startBg from "../assets/start-bg.png";
import endVideo from "../assets/end-video.mp4";
import previewBg from "../assets/preview-bg.jpg";

const API_URL = import.meta.env.VITE_API_URL || "https://photobooth-production-e5fa.up.railway.app";

const STATES = {
  IDLE: "IDLE",
  POLLING: "POLLING",
  READY: "READY",
  COUNTDOWN: "COUNTDOWN",
  CAPTURE: "CAPTURE",
  PREVIEW: "PREVIEW",
  PROCESS: "PROCESS",
  PRINT: "PRINT",
  EMAIL: "EMAIL",
  COMPLETE: "COMPLETE",
};

export default function App() {
  const [state, setState] = useState(STATES.IDLE);
  const [qrCode, setQrCode] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [countdown, setCountdown] = useState(3);
  const [photoIndex, setPhotoIndex] = useState(0);
  const [photos, setPhotos] = useState([]);
  const [stripPreview, setStripPreview] = useState("");
  const [sheetPath, setSheetPath] = useState("");
  const [email, setEmail] = useState("");
  const [flash, setFlash] = useState(false);
  const [pollingSince, setPollingSince] = useState("");
  const [error, setError] = useState("");
  const [printQty, setPrintQty] = useState(0);
  const [downloadQty, setDownloadQty] = useState(0);
  const [qrPos, setQrPos] = useState({ x: 0, y: 0 });
  const [adminTaps, setAdminTaps] = useState(0);
  const adminTimerRef = useRef(null);
  const dragRef = useRef(null);

  const videoRef = useRef(null);
  const countdownRef = useRef(null);
  const streamRef = useRef(null);
  const pollingRef = useRef(null);

  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  }, []);

  const startCamera = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1920 }, height: { ideal: 1080 } },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
      stream.getVideoTracks().forEach((track) => {
        track.onended = () => {
          setError("Camera disconnected. Restarting...");
          stopCamera();
          setTimeout(() => setState(STATES.IDLE), 3000);
        };
      });
    } catch (err) {
      setError("Camera not found. Connect Canon R100 via USB in webcam mode.");
      setTimeout(() => setState(STATES.IDLE), 5000);
    }
  }, [stopCamera]);

  const captureFrame = useCallback(() => {
    const video = videoRef.current;
    if (!video) return null;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth || 1920;
    canvas.height = video.videoHeight || 1080;
    canvas.getContext("2d").drawImage(video, 0, 0);
    return canvas.toDataURL("image/jpeg", 0.95);
  }, []);

  const fetchQR = useCallback(async () => {
    try {
      const res = await axios.get(`${API_URL}/qr/generate`);
      setQrCode(res.data.qr_code);
      setPollingSince(new Date().toISOString());
      setState(STATES.POLLING);
    } catch {
      setError("Cannot reach server. Check connection.");
      setTimeout(() => {
        setError("");
        setState(STATES.IDLE);
      }, 5000);
    }
  }, []);

  // Dev shortcuts: 1=IDLE 2=POLLING 3=READY 4=COUNTDOWN 5=CAPTURE 6=PREVIEW 7=PROCESS 8=PRINT 9=COMPLETE
  useEffect(() => {
    if (import.meta.env.PROD) return;
    const handler = (e) => {
      const map = {
        "1": STATES.IDLE, "2": STATES.POLLING, "3": STATES.READY,
        "4": STATES.COUNTDOWN, "5": STATES.CAPTURE, "6": STATES.PREVIEW,
        "7": STATES.PROCESS, "8": STATES.PRINT, "9": STATES.COMPLETE,
      };
      if (map[e.key]) setState(map[e.key]);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => {
    if (state === STATES.IDLE) {
      setPhotos([]);
      setStripPreview("");
      setSheetPath("");
      setEmail("");
      setPhotoIndex(0);
      setPrintQty(0);
      setDownloadQty(0);
      setError("");
      fetchQR();
    }
  }, [state, fetchQR]);

  useEffect(() => {
    if (state !== STATES.POLLING) return;
    pollingRef.current = setInterval(async () => {
      try {
        const res = await axios.get(`${API_URL}/session/latest`, { params: { since: pollingSince } });
        if (res.data.valid) {
          setSessionId(res.data.session_id);
          setPrintQty(res.data.print_qty || 0);
          setDownloadQty(res.data.download_qty || 0);
          clearInterval(pollingRef.current);
          setState(STATES.READY);
        }
      } catch {}
    }, 2000);
    return () => clearInterval(pollingRef.current);
  }, [state, pollingSince]);

  useEffect(() => {
    if (state !== STATES.COUNTDOWN) return;
    if (countdownRef.current) {
      countdownRef.current.currentTime = 0;
      countdownRef.current.play().catch(() => {});
    }
  }, [state, photoIndex]);

  useEffect(() => {
    if (state !== STATES.CAPTURE) return;

    const doCapture = async () => {
      const track = streamRef.current?.getVideoTracks()[0];
      if (!track || track.readyState !== "live") {
        setError("Camera lost. Restarting...");
        stopCamera();
        setTimeout(() => setState(STATES.IDLE), 3000);
        return;
      }

      setFlash(true);
      setTimeout(() => setFlash(false), 200);

      const frame = captureFrame();
      if (!frame) return;

      setPhotos((prev) => [...prev, frame]);
      setState(STATES.PREVIEW);
    };

    const timer = setTimeout(doCapture, 300);
    return () => clearTimeout(timer);
  }, [state, captureFrame, stopCamera]);

  useEffect(() => {
    if (state !== STATES.PREVIEW) return;
    const timer = setTimeout(() => {
      if (photos.length >= 4) {
        stopCamera();
        setState(STATES.PROCESS);
      } else {
        setPhotoIndex((i) => i + 1);
        setState(STATES.COUNTDOWN);
      }
    }, 5000);
    return () => clearTimeout(timer);
  }, [state, photos.length, stopCamera]);

  useEffect(() => {
    if (state !== STATES.PROCESS) return;
    if (photos.length < 4) return;

    const process = async () => {
      try {
        let strip;
        if (window.booth) {
          const result = await window.booth.createStrip(photos);
          strip = result.stripBase64;
          setStripPreview(strip);
          setSheetPath(result.sheetPath);
        } else {
          strip = photos[0];
          setStripPreview(strip);
        }

        axios.post(`${API_URL}/photos/upload`, {
          session_id: sessionId,
          image: strip,
        }).catch((err) => console.error("Photo backup failed:", err));

        setState(STATES.PRINT);
      } catch (err) {
        setError("Failed to create strip: " + err.message);
        setTimeout(() => setState(STATES.IDLE), 5000);
      }
    };
    process();
  }, [state, photos]);

  useEffect(() => {
    if (state !== STATES.PRINT) return;

    const print = async () => {
      if (printQty > 0) {
        try {
          if (window.booth && sheetPath) {
            const result = await window.booth.printStrip(sheetPath);
            if (result && !result.success) {
              setError("Print issue — staff has been notified.");
            }
          }
        } catch (err) {
          console.error("Print failed:", err);
          setError("Print issue — staff has been notified.");
        }
      }

      if (downloadQty > 0 && stripPreview) {
        try {
          await axios.post(`${API_URL}/email/send`, {
            session_id: sessionId,
            image: stripPreview,
          });
        } catch (err) {
          console.error("Email failed:", err);
          setError("Email delivery failed. Visit the booth for help.");
        }
      }

      setTimeout(() => setState(STATES.COMPLETE), 3000);
    };
    print();
  }, [state, sheetPath, printQty, downloadQty, stripPreview, sessionId]);

  const handleStart = async () => {
    try {
      await axios.post(`${API_URL}/session/start/${sessionId}`);
      await startCamera();
      setState(STATES.COUNTDOWN);
    } catch (err) {
      setError("Session error. Please try again.");
      setTimeout(() => setState(STATES.IDLE), 3000);
    }
  };

  const handleAdminTap = useCallback(() => {
    setAdminTaps((prev) => {
      const next = prev + 1;
      if (next >= 5) {
        if (window.booth?.exitKiosk) window.booth.exitKiosk();
        return 0;
      }
      clearTimeout(adminTimerRef.current);
      adminTimerRef.current = setTimeout(() => setAdminTaps(0), 3000);
      return next;
    });
  }, []);

  const endVideoRef = useRef(null);

  useEffect(() => {
    if (state !== STATES.COMPLETE) return;
    if (endVideoRef.current) {
      endVideoRef.current.currentTime = 0;
      endVideoRef.current.play().catch(() => {});
    }
    const fallback = setTimeout(() => setState(STATES.IDLE), 10000);
    return () => clearTimeout(fallback);
  }, [state]);

  return (
    <div className="h-screen w-screen flex flex-col items-center justify-center bg-cream font-body relative overflow-hidden">
      {flash && (
        <div className="fixed inset-0 bg-white z-50 animate-pulse" />
      )}

      <div
        className="fixed top-0 right-0 w-16 h-16 z-[100]"
        onClick={handleAdminTap}
      />

      {error && (
        <div className="fixed top-8 left-1/2 -translate-x-1/2 bg-red-800 text-white px-8 py-4 rounded-lg text-xl z-40">
          {error}
        </div>
      )}

      {(state === STATES.IDLE || state === STATES.POLLING) && (
        <div className="fixed inset-0">
          <img
            src={homeBg}
            alt=""
            className="w-full h-full object-cover"
          />
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <div
              ref={dragRef}
              style={{ transform: `translate(${qrPos.x}px, ${qrPos.y}px)` }}
              className="mt-[8%] cursor-grab active:cursor-grabbing touch-none"
              onPointerDown={(e) => {
                const el = e.currentTarget;
                el.setPointerCapture(e.pointerId);
                const startX = e.clientX - qrPos.x;
                const startY = e.clientY - qrPos.y;
                const onMove = (ev) => setQrPos({ x: ev.clientX - startX, y: ev.clientY - startY });
                const onUp = () => {
                  el.removeEventListener("pointermove", onMove);
                  el.removeEventListener("pointerup", onUp);
                };
                el.addEventListener("pointermove", onMove);
                el.addEventListener("pointerup", onUp);
              }}
            >
              {qrCode ? (
                <img
                  src={`data:image/png;base64,${qrCode}`}
                  alt="Scan to pay"
                  className="w-40 h-40 rounded-lg shadow-2xl"
                />
              ) : (
                <div className="w-40 h-40 rounded-lg bg-white/20 backdrop-blur animate-pulse" />
              )}
            </div>
          </div>
        </div>
      )}

      {state === STATES.READY && (
        <button
          onClick={handleStart}
          className="fixed inset-0 active:scale-[0.98] transition-transform duration-200"
        >
          <img
            src={startBg}
            alt=""
            className="w-full h-full object-cover"
          />
        </button>
      )}

      {(state === STATES.COUNTDOWN || state === STATES.CAPTURE) && (
        <div className="fixed inset-0 bg-black">
          <video
            ref={countdownRef}
            src={countdownVideo}
            playsInline
            className="w-full h-full object-cover"
            onEnded={() => setState(STATES.CAPTURE)}
          />
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className="hidden"
          />
          <p className="absolute bottom-8 left-1/2 -translate-x-1/2 text-white/60 text-lg">
            Photo {photoIndex + 1} of 4
          </p>
        </div>
      )}

      {state === STATES.PREVIEW && photos.length > 0 && (
        <div className="fixed inset-0 flex items-center justify-center">
          <img
            src={previewBg}
            alt=""
            className="absolute inset-0 w-full h-full object-cover"
          />
          <img
            src={photos[photos.length - 1]}
            alt="Preview"
            className="relative z-10 rounded-2xl shadow-2xl object-cover"
            style={{ width: "28%", aspectRatio: "4/3" }}
          />
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className="hidden"
          />
        </div>
      )}

      {state === STATES.PROCESS && (
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-burgundy border-t-transparent rounded-full animate-spin mx-auto mb-8" />
          <p className="text-3xl text-burgundy font-display">
            Creating your strip...
          </p>
        </div>
      )}

      {state === STATES.PRINT && (
        <div className="text-center flex flex-col items-center gap-8">
          {stripPreview && (
            <img
              src={stripPreview}
              alt="Your photo strip"
              className="h-[60vh] rounded-lg shadow-2xl"
            />
          )}
          <p className="text-3xl text-burgundy font-display">Printing...</p>
        </div>
      )}


      {state === STATES.COMPLETE && (
        <div className="fixed inset-0 bg-black">
          <video
            ref={endVideoRef}
            src={endVideo}
            playsInline
            className="w-full h-full object-cover"
            onEnded={() => setState(STATES.IDLE)}
          />
        </div>
      )}
    </div>
  );
}
