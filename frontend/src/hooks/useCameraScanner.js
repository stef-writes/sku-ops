import { useRef, useState, useCallback, useEffect } from "react";
import { Html5Qrcode, Html5QrcodeSupportedFormats } from "html5-qrcode";

const DEFAULT_FORMATS = [
  Html5QrcodeSupportedFormats.UPC_A,
  Html5QrcodeSupportedFormats.EAN_13,
  Html5QrcodeSupportedFormats.CODE_128,
  Html5QrcodeSupportedFormats.QR_CODE,
];

const DEBOUNCE_MS = 500;

/**
 * Manages camera lifecycle for barcode scanning via html5-qrcode.
 *
 * Does NOT perform product lookup — it only decodes barcodes and
 * calls onScan(code). Wire onScan to useBarcodeScanner.submit(code)
 * in the parent to keep lookup logic in one place.
 *
 * @param {object} options
 * @param {(code: string) => void} options.onScan - decoded barcode string
 * @param {Array} [options.formats] - Html5QrcodeSupportedFormats array
 */
export function useCameraScanner({ onScan, formats = DEFAULT_FORMATS } = {}) {
  const scannerRef = useRef(null);
  const lastCodeRef = useRef(null);
  const lastTimeRef = useRef(0);
  const onScanRef = useRef(onScan);
  const [active, setActive] = useState(false);
  const [error, setError] = useState(null);
  const elementId = useRef(`camera-scanner-${Math.random().toString(36).slice(2, 8)}`);

  useEffect(() => {
    onScanRef.current = onScan;
  }, [onScan]);

  const stop = useCallback(async () => {
    try {
      if (scannerRef.current) {
        const state = scannerRef.current.getState();
        if (state === 2) await scannerRef.current.stop();
        scannerRef.current.clear();
        scannerRef.current = null;
      }
    } catch {
      scannerRef.current = null;
    }
    setActive(false);
  }, []);

  const start = useCallback(async () => {
    setError(null);

    if (scannerRef.current) await stop();

    const el = document.getElementById(elementId.current);
    if (!el) {
      setError("Scanner element not found");
      return;
    }

    try {
      const scanner = new Html5Qrcode(elementId.current, {
        formatsToSupport: formats,
        verbose: false,
      });
      scannerRef.current = scanner;

      await scanner.start(
        { facingMode: "environment" },
        { fps: 10, qrbox: { width: 250, height: 150 }, aspectRatio: 1.333 },
        (decodedText) => {
          const now = Date.now();
          if (decodedText === lastCodeRef.current && now - lastTimeRef.current < DEBOUNCE_MS) return;
          lastCodeRef.current = decodedText;
          lastTimeRef.current = now;
          onScanRef.current?.(decodedText);
        },
      );

      setActive(true);
    } catch (err) {
      scannerRef.current = null;
      const msg = typeof err === "string" ? err : err?.message || "Camera not available";
      if (msg.includes("NotAllowedError") || msg.includes("Permission")) {
        setError("Camera permission denied. Allow camera access in your browser settings.");
      } else {
        setError(msg);
      }
    }
  }, [formats, stop]);

  useEffect(() => {
    return () => {
      if (scannerRef.current) {
        try {
          const state = scannerRef.current.getState();
          if (state === 2) scannerRef.current.stop();
          scannerRef.current.clear();
        } catch { /* unmount cleanup — best effort */ }
        scannerRef.current = null;
      }
    };
  }, []);

  return { elementId: elementId.current, start, stop, active, error };
}
