// orbSurface.glsl — Living Orb Inner Core + Outer Glow
// Matches Canvas2DFallback 3-ring system: inner core (0.85x), mid ring (1.15x), outer ring (1.45x)
// This shader renders the INNER CORE with radial gradient, specular highlight, noise overlay, and aperture mask

varying vec3 vNormal;
varying vec2 vUv;
varying vec3 vWorldPosition;
varying vec3 vViewPosition;

uniform float uTime;
uniform float uMicLevel;
uniform vec3 uStateColor;       // Primary state color
uniform vec3 uStateGlow;        // Glow color
uniform vec3 uAccentColor;      // Accent/brand color
uniform float uAperture;        // 0-1 aperture size (0 = fully closed, 1 = fully open)
uniform vec2 uNoiseOffset;      // Noise animation offset
uniform float uPulseScale;      // Pulse scale factor
uniform float uState;           // State enum: 0=idle, 1=listening, 2=speaking, 3=processing, 4=error, 5=muted

// Simplex 3D noise (Stefan Gustavson)
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

// Hash for pseudo-random
float hash(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

void main() {
  // Calculate view direction and fresnel
  vec3 viewDir = normalize(cameraPosition - vWorldPosition);
  float fresnel = pow(1.0 - max(dot(viewDir, vNormal), 0.0), 3.0);

  // UV coordinates centered at 0.5
  vec2 centeredUv = vUv - 0.5;
  float distFromCenter = length(centeredUv) * 2.0; // 0 to 1 at edge

  // Base colors from state
  vec3 coreColor = uStateColor;
  vec3 glowColor = uStateGlow;
  vec3 accentColor = uAccentColor;

  // ==========================================
  // RADIAL GRADIENT: Inner Core (0.0 - 0.85)
  // ==========================================
  vec3 color = vec3(0.0);
  float alpha = 0.0;

  // Inner core radial gradient (matches Canvas2DFallback)
  if (distFromCenter < 0.85) {
    float t = distFromCenter / 0.85; // 0 at center, 1 at inner edge

    // Three-stop radial gradient: center -> mid -> edge
    vec3 centerColor = coreColor * 1.2;           // Brighter center
    vec3 midColor = coreColor;                    // Main state color
    vec3 edgeColor = mix(coreColor, accentColor, 0.3); // Blend toward accent

    if (t < 0.5) {
      color = mix(centerColor, midColor, t * 2.0);
    } else {
      color = mix(midColor, edgeColor, (t - 0.5) * 2.0);
    }

    // Specular highlight (top-left)
    vec2 highlightPos = vec2(-0.15, -0.15);
    float highlightDist = length(centeredUv - highlightPos) * 2.0;
    float highlight = pow(max(1.0 - highlightDist, 0.0), 8.0) * 0.4;
    color += vec3(highlight);

    alpha = 0.95;
  }

  // MID RING ZONE (0.85 - 1.15) - rendered by orbMidRing.glsl, but we add subtle glow here
  // OUTER RING ZONE (1.15 - 1.45) - subtle atmospheric glow

  // ==========================================
  // NOISE OVERLAY on inner core
  // ==========================================
  if (distFromCenter < 0.85 && uState != 5.0) { // Not muted
    float noise = snoise(vec3(vUv * 10.0 + uNoiseOffset, uTime * 0.05));
    noise = noise * 0.5 + 0.5; // 0-1
    color += coreColor * noise * 0.08;
  }

  // ==========================================
  // APERTURE MASK (animated circular clip)
  // ==========================================
  if (uAperture < 1.0) {
    float apertureEdge = uAperture * 0.85; // Aperture affects inner core radius
    float mask = smoothstep(apertureEdge - 0.02, apertureEdge + 0.02, distFromCenter);
    alpha *= mask;
    color *= mask;
  }

  // ==========================================
  // STATE-SPECIFIC EMISSIVE
  // ==========================================
  float emissive = 0.0;
  if (uState == 2.0) { // speaking - pulse with mic level
    float pulse = sin(uTime * 4.0) * 0.5 + 0.5;
    emissive = pulse * uMicLevel * 0.3;
  } else if (uState == 4.0) { // error - fast red pulse
    float pulse = sin(uTime * 8.0) * 0.5 + 0.5;
    emissive = 0.3 + pulse * 0.3;
  } else if (uState == 3.0) { // processing - slow breathing
    emissive = sin(uTime * 1.5) * 0.1 + 0.15;
  } else if (uState == 1.0) { // listening - subtle pulse
    emissive = sin(uTime * 2.0) * 0.05 + 0.1;
  }

  // Fresnel glow on edges (but masked by aperture)
  float edgeGlow = fresnel * 0.6;
  if (uAperture < 1.0) {
    float apertureEdge = uAperture * 0.85;
    edgeGlow *= smoothstep(apertureEdge - 0.05, apertureEdge + 0.05, distFromCenter);
  }

  // Final color composition
  vec3 finalColor = color + glowColor * (edgeGlow + emissive * 0.5);
  float finalAlpha = alpha * (1.0 - emissive * 0.2); // Slight transparency when emissive

  // Muted state
  if (uState == 5.0) {
    finalColor = coreColor * 0.4;
    finalAlpha = 0.5;
  }

  gl_FragColor = vec4(finalColor, finalAlpha);
}