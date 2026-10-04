import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';

// ── Mock Three.js ────────────────────────────────────────────────────────────
// jsdom has no WebGL, so we mock THREE with class-based constructors.
const mockDispose = vi.fn();
const mockForceContextLoss = vi.fn();
const mockSetSize = vi.fn();
const mockSetPixelRatio = vi.fn();
const mockRender = vi.fn();
const mockDomElement = document.createElement('canvas');

vi.mock('three', () => {
  class Color { constructor() {} }
  class Scene {
    background: any = null;
    add = vi.fn();
  }
  class OrthographicCamera {
    position = { set: vi.fn() };
    left = 0; right = 0; top = 0; bottom = 0;
    updateProjectionMatrix = vi.fn();
    constructor() {}
  }
  class WebGLRenderer {
    setSize = mockSetSize;
    setPixelRatio = mockSetPixelRatio;
    render = mockRender;
    dispose = mockDispose;
    forceContextLoss = mockForceContextLoss;
    domElement = mockDomElement;
    constructor() {}
  }
  class PlaneGeometry { constructor() {} }
  class CircleGeometry { constructor() {} }
  class RingGeometry { constructor() {} }
  class BufferGeometry {
    setAttribute = vi.fn();
    setFromPoints = vi.fn();
    setDrawRange = vi.fn();
    dispose = vi.fn();
    constructor() {}
  }
  class MeshBasicMaterial {
    dispose = vi.fn();
    opacity = 1;
    constructor() {}
  }
  class LineBasicMaterial {
    dispose = vi.fn();
    opacity = 0;
    constructor() {}
  }
  class PointsMaterial { constructor() {} }
  class Mesh {
    position = { set: vi.fn() };
    scale = { set: vi.fn() };
    add = vi.fn();
    material: any = { opacity: 1 };
    geometry: any = {};
    children: any[] = [];
    constructor() {}
  }
  class Line {
    geometry = { setDrawRange: vi.fn(), dispose: vi.fn() };
    material = { dispose: vi.fn(), opacity: 0 };
    userData: any = {};
    constructor() {}
  }
  class Points {
    rotation = { z: 0 };
    constructor() {}
  }
  class Group {
    children: any[] = [];
    add = vi.fn();
    remove = vi.fn();
    constructor() {}
  }
  class AmbientLight {
    position = { set: vi.fn() };
    constructor() {}
  }
  class PointLight {
    position = { set: vi.fn() };
    constructor() {}
  }
  class TextureLoader {
    load = vi.fn();
    constructor() {}
  }
  class Vector3 { constructor() {} }
  class Float32BufferAttribute { constructor() {} }
  class BufferAttribute { constructor() {} }

  return {
    Color, Scene, OrthographicCamera, WebGLRenderer,
    PlaneGeometry, CircleGeometry, RingGeometry, BufferGeometry,
    MeshBasicMaterial, LineBasicMaterial, PointsMaterial,
    Mesh, Line, Points, Group,
    AmbientLight, PointLight, TextureLoader, Vector3,
    Float32BufferAttribute, BufferAttribute,
    DoubleSide: 2,
  };
});

// Mock child components to keep tests focused
vi.mock('../HealthIndicator', () => ({
  HealthIndicator: () => <div data-testid="health-indicator">health</div>,
}));
vi.mock('../SignatureWatermark', () => ({
  SignatureWatermark: ({ className }: { className?: string }) => (
    <div data-testid="signature-watermark" className={className}>sig</div>
  ),
}));
// Mock the earth texture import
vi.mock('../../assets/earth-dark.jpg', () => ({ default: 'earth-dark-mock.jpg' }));

// Import after mocks are set up
import { FlatMapAuthBackground } from '../FlatMapAuthBackground';

describe('FlatMapAuthBackground', () => {
  it('renders without throwing (no WebGL errors)', () => {
    expect(() => render(<FlatMapAuthBackground />)).not.toThrow();
  });

  it('renders the fixed container div', () => {
    const { container } = render(<FlatMapAuthBackground />);
    const root = container.firstElementChild as HTMLElement;
    expect(root.className).toContain('fixed');
    expect(root.className).toContain('inset-0');
  });

  it('renders HealthIndicator sub-component', () => {
    render(<FlatMapAuthBackground />);
    expect(screen.getByTestId('health-indicator')).toBeInTheDocument();
  });

  it('renders SignatureWatermark sub-component', () => {
    render(<FlatMapAuthBackground />);
    expect(screen.getByTestId('signature-watermark')).toBeInTheDocument();
  });

  it('renders login gradient by default', () => {
    const { container } = render(<FlatMapAuthBackground />);
    const gradientDiv = container.querySelector('.transition-all.duration-700') as HTMLElement;
    expect(gradientDiv?.style.background).toContain('#0A0D12');
  });

  it('renders signup gradient when variant="signup"', () => {
    const { container } = render(<FlatMapAuthBackground variant="signup" />);
    const gradientDiv = container.querySelector('.transition-all.duration-700') as HTMLElement;
    expect(gradientDiv?.style.background).toContain('#0D1117');
  });

  it('appends WebGL canvas to the container on mount', () => {
    const { container } = render(<FlatMapAuthBackground />);
    // The mocked renderer's domElement (a canvas) should be in the DOM
    const canvasElements = container.querySelectorAll('canvas');
    expect(canvasElements.length).toBeGreaterThanOrEqual(1);
  });
});
