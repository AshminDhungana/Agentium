import '@testing-library/jest-dom';
import '@/test/a11y';
import { vi } from 'vitest';

if (!window.matchMedia) {
  window.matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }) as unknown as MediaQueryList;
}

// ResizeObserver polyfill for jsdom
if (!window.ResizeObserver) {
  window.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// MediaDevices getUserMedia polyfill for jsdom
Object.defineProperty(navigator, 'mediaDevices', {
  value: {
    getUserMedia: vi.fn().mockResolvedValue({
      getTracks: () => [{ stop: vi.fn() }],
      getAudioTracks: () => [{ enabled: true, stop: vi.fn() }],
    }),
  },
  configurable: true,
});

// Canvas getContext mock for jsdom (without canvas npm package)
const originalCreateElement = document.createElement.bind(document);

const createMockContext = () => ({
  fillRect: vi.fn(),
  clearRect: vi.fn(),
  beginPath: vi.fn(),
  arc: vi.fn(),
  fill: vi.fn(),
  stroke: vi.fn(),
  moveTo: vi.fn(),
  lineTo: vi.fn(),
  closePath: vi.fn(),
  createRadialGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
  createLinearGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
  createConicGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
  save: vi.fn(),
  restore: vi.fn(),
  translate: vi.fn(),
  scale: vi.fn(),
  fillText: vi.fn(),
  measureText: vi.fn(() => ({ width: 50 })),
  fillStyle: '',
  strokeStyle: '',
  lineWidth: 1,
  globalAlpha: 1,
  font: '14px system-ui',
  textAlign: 'center',
  textBaseline: 'middle',
  shadowColor: '',
  shadowBlur: 0,
  lineCap: 'round',
  lineJoin: 'round',
  quadraticCurveTo: vi.fn(),
  bezierCurveTo: vi.fn(),
  rect: vi.fn(),
  clip: vi.fn(),
  drawImage: vi.fn(),
  getImageData: vi.fn(() => ({ data: new Uint8ClampedArray(), width: 0, height: 0 })),
  putImageData: vi.fn(),
  createImageData: vi.fn(),
  canvas: { width: 0, height: 0 } as HTMLCanvasElement,
  globalCompositeOperation: 'source-over',
  // Required methods for full interface
  isPointInPath: vi.fn(),
  isPointInStroke: vi.fn(),
  transform: vi.fn(),
  setTransform: vi.fn(),
  resetTransform: vi.fn(),
  createPattern: vi.fn(),
  direction: 'inherit',
  filter: 'none',
  imageSmoothingEnabled: true,
  imageSmoothingQuality: 'low',
  lineDashOffset: 0,
  getLineDash: vi.fn(() => []),
  setLineDash: vi.fn(),
  miterLimit: 10,
  strokeText: vi.fn(),
  transferFromImageBitmap: vi.fn(),
  arcTo: vi.fn(),
  ellipse: vi.fn(),
  roundRect: vi.fn(),
});

vi.spyOn(document, 'createElement').mockImplementation((tag) => {
  if (tag === 'canvas') {
    const canvas = originalCreateElement('canvas');
    canvas.getContext = vi.fn(() => createMockContext() as any);
    return canvas;
  }
  return originalCreateElement(tag);
});
