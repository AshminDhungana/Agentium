// orbMidRing.glsl — Living Orb Mid Ring (Brand Ring)
// Conic gradient + blob distortion + rotation
// Renders at 1.15x base radius

varying vec3 vNormal;
varying vec2 vUv;
varying vec3 vWorldPosition;
varying vec3 vViewPosition;

uniform float uTime;
uniform float uMicLevel;
uniform vec3 uStateColor;       // Primary state color
uniform vec3 uBrandColor;       // Brand primary
uniform vec3 uAccentColor;      // Brand secondary/accent
uniform float uRingRotation;    // Ring rotation in radians
uniform float uBlobAmount;      // Blob distortion intensity
uniform float uPulseScale;      // Pulse scale
uniform float uState;           // State enum: 0=idle, 1=listening, 2=speaking, 3=processing, 4=error, 5=muted

// Simplex 3D noise for blob distortion
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
  // UV coordinates centered
  vec2 centeredUv = vUv - 0.5;
  float dist = length(centeredUv) * 2.0; // 0 to 1 at quad edge

  // The mid ring lives at specific radius range (0.85 to 1.15 of base)
  // We render a quad and clip to the ring band
  float innerRadius = 0.85;
  float outerRadius = 1.15;

  // Only render within the ring band
  if (dist < innerRadius || dist > outerRadius) {
    discard;
  }

  // Normalize within ring (0 at inner, 1 at outer)
  float ringProgress = (dist - innerRadius) / (outerRadius - innerRadius);

  // ==========================================
  // CONIC GRADIENT (rotating)
  // ==========================================
  // Calculate angle for conic gradient
  float angle = atan(centeredUv.y, centeredUv.x) + uRingRotation;
  angle = angle / (2.0 * 3.14159265359) + 0.5; // 0 to 1

  // Three-way blend: stateColor -> brandColor -> accentColor -> stateColor
  vec3 conicColor;
  if (angle < 0.33) {
    conicColor = mix(uStateColor, uBrandColor, angle * 3.0);
  } else if (angle < 0.66) {
    conicColor = mix(uBrandColor, uAccentColor, (angle - 0.33) * 3.0);
  } else {
    conicColor = mix(uAccentColor, uStateColor, (angle - 0.66) * 3.0);
  }

  // ==========================================
  // BLOB DISTORTION
  // ==========================================
  // Multiple frequency noise for organic blob shape
  float blobNoise = 0.0;
  blobNoise += snoise(vec3(centeredUv * 3.0 + vec2(uRingRotation * 0.5, 0.0), uTime * 0.3)) * 0.5;
  blobNoise += snoise(vec3(centeredUv * 7.0 + vec2(0.0, uRingRotation * 0.3), uTime * 0.5)) * 0.3;
  blobNoise += snoise(vec3(centeredUv * 13.0 + vec2(uRingRotation * 0.2, uRingRotation * 0.4), uTime * 0.7)) * 0.2;

  // Apply blob distortion to ring edges
  float blobDistortion = blobNoise * uBlobAmount;

  // Modulate ring edge based on blob
  float innerEdge = innerRadius + blobDistortion * 0.08;
  float outerEdge = outerRadius + blobDistortion * 0.08;

  // Soft edges
  float innerMask = smoothstep(innerEdge - 0.015, innerEdge + 0.015, dist);
  float outerMask = 1.0 - smoothstep(outerEdge - 0.015, outerEdge + 0.015, dist);
  float edgeMask = innerMask * outerMask;

  // Radial gradient within ring (brighter at outer edge for brand emphasis)
  float radialGlow = mix(0.3, 1.0, ringProgress);

  // Mic level modulation - ring thickens/brightens with audio
  float audioBoost = 1.0 + uMicLevel * 0.4;
  edgeMask *= audioBoost;

  // ==========================================
  // STATE-SPECIFIC BEHAVIOR
  // ==========================================
  float stateIntensity = 1.0;
  float pulseAmount = 0.0;

  if (uState == 1.0) { // listening - rotates faster, pulses with mic
    pulseAmount = sin(uTime * 3.0 + uMicLevel * 10.0) * 0.5 + 0.5;
    stateIntensity = 0.7 + pulseAmount * 0.3;
  } else if (uState == 2.0) { // speaking - bright, steady rotation
    stateIntensity = 1.0;
    pulseAmount = sin(uTime * 5.0) * 0.3 + 0.7;
  } else if (uState == 3.0) { // processing - swirling, faster rotation
    pulseAmount = sin(uTime * 2.0) * 0.5 + 0.5;
    stateIntensity = 0.8 + pulseAmount * 0.2;
  } else if (uState == 4.0) { // error - red tinge, erratic
    pulseAmount = sin(uTime * 7.0) * 0.5 + 0.5;
    conicColor = mix(conicColor, vec3(1.0, 0.2, 0.2), 0.3);
    stateIntensity = 0.9;
  } else if (uState == 5.0) { // muted - dim, no rotation (handled by uRingRotation=0)
    stateIntensity = 0.3;
    conicColor = conicColor * 0.5;
  }

  // Final color with conic gradient
  vec3 finalColor = conicColor * radialGlow * stateIntensity;

  // Add subtle radial highlight
  float highlight = pow(max(1.0 - ringProgress, 0.0), 3.0) * 0.2;
  finalColor += uBrandColor * highlight * stateIntensity;

  float finalAlpha = edgeMask * 0.7 * stateIntensity;

  // Modulate by pulse scale
  finalAlpha *= uPulseScale;

  gl_FragColor = vec4(finalColor, finalAlpha);
}