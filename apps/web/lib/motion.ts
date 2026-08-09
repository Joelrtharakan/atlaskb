// A user preference to freeze the atlas motion, independent of the OS
// prefers-reduced-motion. Persisted in localStorage and read by useCapabilities,
// so toggling it in Settings freezes/unfreezes every 3D treatment site-wide.
const KEY = "atlaskb.motion"; // "off" = motion disabled

export function motionDisabled(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(KEY) === "off";
}

export function setMotionDisabled(disabled: boolean): void {
  window.localStorage.setItem(KEY, disabled ? "off" : "on");
  window.dispatchEvent(new Event("atlaskb-motion"));
}

export function subscribeMotion(cb: () => void): () => void {
  window.addEventListener("atlaskb-motion", cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener("atlaskb-motion", cb);
    window.removeEventListener("storage", cb);
  };
}
