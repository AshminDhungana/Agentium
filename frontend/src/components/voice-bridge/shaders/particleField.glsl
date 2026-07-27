// particleField.glsl — Living Orb Particle Field (GPU)
// Renders 200-400 GPU particles as points with size/opacity by distance
// Particles orbit the orb with speeds modulated by audio level

uniform float uTime;
uniform float uMicLevel;
uniform vec3 uStateColor;
uniform float uParticleCount;
uniform float uPulseScale;
uniform float uState;      // 0=idle, 1=listening, 2=speaking, 3=processing, 4=error, 5=muted

attribute float aAngle;       // Initial angle around orb
attribute float aRadius;      // Base radius from center
attribute float aSpeed;       // Angular speed
attribute float aSize;        // Base particle size
attribute float aOpacity;     // Base opacity
attribute float aPhase;       // Phase offset for vertical oscillation
attribute float aInclination; // Inclination for 3D spherical distribution

varying float vOpacity;
varying vec3 vColor;
varying float vParticleSize;
varying float vDistFromCenter;

// Simplex noise for organic motion (optional - can use sin/cos for performance)
vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 permute(vec4 x) { return mod289(((x * 34.0) + 1.0) * x); }
vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }

float snoise(vec3 v) {
  const vec2 C = vec2(1.0/6.0, 1.0/3.0);
  const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
  vec3 i = floor(v + dot(v, C.yyy));
  vec3 x0 = v - i + dot(i, C.xxx);
  vec3 g = step(x0.yzx, x0.xyz);
  vec3 l = 1.0 - g;
  vec3 i1 = min(g.xyz, l.zxy);
  vec3 i2 = max(g.xyz, l.zxy);
  vec3 x1 = x0 - i1 + C.xxx;
  vec3 x2 = x0 - i2 + C.yyy;
  vec3 x3 = x0 - D.yyy;
  i = mod289(i);
  vec4 p = permute(permute(permute(i.z + vec4(0.0, i1.z, i2.z, 1.0))
    + i.y + vec4(0.0, i1.y, i2.y, 1.0))
    + i.x + vec4(0.0, i1.x, i2.x, 1.0));
  float n_ = 0.142857142857;
  vec3 ns = n_ * D.wyz - D.xzx;
  vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
  vec4 x_ = floor(j * ns.z);
  vec4 y_ = floor(j - 7.0 * x_);
  vec4 x = x_ * ns.x + ns.yyyy;
  vec4 y = y_ * ns.x + ns.yyyy;
  vec4 h = 1.0 - abs(x) - abs(y);
  vec4 b0 = vec4(x.xy, y.xy);
  vec4 b1 = vec4(x.zw, y.zw);
  vec4 s0 = floor(b0) * 2.0 + 1.0;
  vec4 s1 = floor(b1) * 2.0 + 1.0;
  vec4 sh = -step(h, vec4(0.0));
  vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
  vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;
  vec3 p0 = vec3(a0.xy, h.x);
  vec3 p1 = vec3(a0.zw, h.y);
  vec3 p2 = vec3(a1.xy, h.z);
  vec3 p3 = vec3(a1.zw, h.w);
  vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2,p2), dot(p3,p3)));
  p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
  vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
  m = m * m;
  return 42.0 * dot(m*m, vec4(dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3)));
}

void main() {
  // Normalized time for smooth animation
  float t = uTime;

  // State-based speed modifier
  float stateSpeedMod = 1.0;
  float stateVerticalMod = 1.0;
  float stateNoiseMod = 0.0;

  if (uState == 1.0) { // listening - fast, responsive to audio
    stateSpeedMod = 1.5 + uMicLevel * 2.0;
    stateVerticalMod = 1.0 + uMicLevel * 0.5;
    stateNoiseMod = uMicLevel * 0.3;
  } else if (uState == 2.0) { // speaking - steady, slightly slower
    stateSpeedMod = 1.2;
    stateVerticalMod = 0.8;
  } else if (uState == 3.0) { // processing - swirling, chaotic
    stateSpeedMod = 2.0;
    stateVerticalMod = 1.5;
    stateNoiseMod = 0.4;
  } else if (uState == 4.0) { // error - erratic, fast
    stateSpeedMod = 2.5;
    stateVerticalMod = 1.2;
    stateNoiseMod = 0.5;
  } else if (uState == 5.0) { // muted - frozen/slow
    stateSpeedMod = 0.1;
    stateVerticalMod = 0.1;
  } else { // idle - slow, gentle
    stateSpeedMod = 0.5;
    stateVerticalMod = 0.7;
  }

  // ==========================================
  // POSITION CALCULATION
  // ==========================================

  // Angular position with speed and time
  float angle = aAngle + aSpeed * t * stateSpeedMod * (1.0 + uMicLevel * 3.0);

  // Add subtle noise to angle for organic motion
  if (stateNoiseMod > 0.0) {
    float n = snoise(vec3(aAngle * 0.1, t * 0.2, aRadius * 0.01));
    angle += n * stateNoiseMod * 0.1;
  }

  // Radius with vertical oscillation
  float phase = aPhase + t * 0.02 * stateVerticalMod;
  float radius = aRadius + sin(phase) * aRadius * 0.15;

  // Pulse scale affects radius
  radius *= uPulseScale;

  // 3D position with inclination (spherical distribution)
  float cosIncl = cos(aInclination);
  float sinIncl = sin(aInclination);

  vec3 pos = vec3(
    cos(angle) * radius * cosIncl,
    sin(phase * 0.7) * radius * sinIncl * 0.6, // Flattened Y for elliptical orbit
    sin(angle) * radius * cosIncl
  );

  // ==========================================
  // SIZE CALCULATION
  // ==========================================

  // Distance from camera for perspective size
  vec4 mvPosition = modelViewMatrix * vec4(pos, 1.0);
  float distFromCamera = length(-mvPosition.xyz);

  // Base size modulated by mic level and pulse
  float size = aSize * (1.0 + uMicLevel * 0.5) * uPulseScale;

  // Perspective divide
  size *= (300.0 / distFromCamera);

  // Particles closer to center are slightly larger
  float centerDist = length(pos);
  float centerFactor = 1.0 - (centerDist / radius) * 0.3;
  size *= centerFactor;

  vParticleSize = size;
  vDistFromCenter = centerDist;

  // ==========================================
  // COLOR & OPACITY
  // ==========================================

  // Opacity based on distance from center (fade at edges)
  float edgeFade = smoothstep(radius * 0.9, radius * 1.1, centerDist);
  float opacity = aOpacity * (1.0 - edgeFade) * 0.8;

  // State-based opacity modulation
  if (uState == 5.0) { // muted
    opacity *= 0.3;
  } else if (uState == 4.0) { // error
    opacity *= 1.2;
  }

  vOpacity = opacity;

  // Color: state color with slight variation
  vec3 color = uStateColor;

  // Add subtle hue shift based on particle angle
  float hueShift = sin(angle * 0.5 + t) * 0.05;
  // Simple hue shift by mixing with accent
  color = mix(color, vec3(color.g, color.b, color.r), hueShift * 0.5);

  // Brighten particles moving toward camera
  float facingCamera = max(dot(normalize(-mvPosition.xyz), vec3(0.0, 0.0, 1.0)), 0.0);
  color += uStateColor * facingCamera * 0.3;

  vColor = color;

  // ==========================================
  // FINAL POSITION
  // ==========================================
  gl_Position = projectionMatrix * mvPosition;
  gl_PointSize = max(size, 1.0); // Minimum 1 pixel
}