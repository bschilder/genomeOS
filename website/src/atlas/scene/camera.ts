/** Camera serialization and focus-scoped keyboard controls for Atlas design §11. */

import { Cartesian3, Math as CesiumMath, type Viewer } from 'cesium';

import type { CameraState } from '../url-state';

export type KeyboardCommand =
  | 'pan-left'
  | 'pan-right'
  | 'pan-up'
  | 'pan-down'
  | 'tilt-up'
  | 'tilt-down'
  | 'zoom-in'
  | 'zoom-out';

interface KeyboardInput {
  key: string;
  target: EventTarget | null;
  altKey?: boolean;
  ctrlKey?: boolean;
  metaKey?: boolean;
}

function isEditable(target: EventTarget | null): boolean {
  if (target === null || typeof target !== 'object') return false;
  const element = target as HTMLElement;
  return (
    element.isContentEditable ||
    ['INPUT', 'SELECT', 'TEXTAREA', 'BUTTON'].includes(element.tagName)
  );
}

export function keyboardCommandFor(
  input: KeyboardInput,
): KeyboardCommand | null {
  if (
    isEditable(input.target) ||
    input.altKey ||
    input.ctrlKey ||
    input.metaKey
  )
    return null;
  const commandByKey: Record<string, KeyboardCommand> = {
    '+': 'zoom-in',
    '=': 'zoom-in',
    '-': 'zoom-out',
    ArrowDown: 'pan-down',
    ArrowLeft: 'pan-left',
    ArrowRight: 'pan-right',
    ArrowUp: 'pan-up',
    a: 'pan-left',
    d: 'pan-right',
    e: 'tilt-down',
    q: 'tilt-up',
    s: 'pan-down',
    w: 'pan-up',
  };
  return (
    commandByKey[input.key] ?? commandByKey[input.key.toLowerCase()] ?? null
  );
}

export function cameraState(viewer: Viewer): CameraState | null {
  const cartographic = viewer.camera.positionCartographic;
  const radians = [
    cartographic?.latitude,
    cartographic?.longitude,
    viewer.camera.heading,
    viewer.camera.pitch,
  ];
  if (
    !cartographic ||
    !Number.isFinite(cartographic.height) ||
    radians.some((value) => !Number.isFinite(value))
  ) {
    return null;
  }
  return {
    heading: CesiumMath.toDegrees(viewer.camera.heading),
    height: cartographic.height,
    lat: CesiumMath.toDegrees(cartographic.latitude),
    lon: CesiumMath.toDegrees(cartographic.longitude),
    pitch: CesiumMath.toDegrees(viewer.camera.pitch),
  };
}

export function setCameraState(
  viewer: Viewer,
  state: CameraState,
  animated: boolean,
): void {
  const destination = Cartesian3.fromDegrees(
    state.lon,
    state.lat,
    state.height,
  );
  const orientation = {
    heading: CesiumMath.toRadians(state.heading),
    pitch: CesiumMath.toRadians(state.pitch),
    roll: 0,
  };
  if (animated)
    viewer.camera.flyTo({ destination, duration: 1.2, orientation });
  else viewer.camera.setView({ destination, orientation });
}

function runCommand(viewer: Viewer, command: KeyboardCommand): void {
  const distance = Math.max(
    20_000,
    viewer.camera.positionCartographic.height * 0.06,
  );
  const angle = CesiumMath.toRadians(3);
  const actions: Record<KeyboardCommand, () => void> = {
    'pan-down': () => viewer.camera.moveDown(distance),
    'pan-left': () => viewer.camera.moveLeft(distance),
    'pan-right': () => viewer.camera.moveRight(distance),
    'pan-up': () => viewer.camera.moveUp(distance),
    'tilt-down': () => viewer.camera.lookDown(angle),
    'tilt-up': () => viewer.camera.lookUp(angle),
    'zoom-in': () => viewer.camera.zoomIn(distance),
    'zoom-out': () => viewer.camera.zoomOut(distance),
  };
  actions[command]();
}

export function bindKeyboardCamera(
  viewer: Viewer,
  container: HTMLElement,
): () => void {
  if (!container.hasAttribute('tabindex')) container.tabIndex = 0;
  const listener = (event: KeyboardEvent) => {
    const command = keyboardCommandFor(event);
    if (command === null) return;
    event.preventDefault();
    runCommand(viewer, command);
  };
  container.addEventListener('keydown', listener);
  return () => container.removeEventListener('keydown', listener);
}
