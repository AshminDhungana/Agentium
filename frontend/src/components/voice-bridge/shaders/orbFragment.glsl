varying vec3 vNormal;
varying vec2 vUv;
varying vec3 vWorldPosition;
varying vec3 vViewPosition;

uniform vec3 uCoreColor;
uniform vec3 uGlowColor;
uniform float uTime;
uniform float uBass;
uniform float uPulsePhase;
uniform float uState;
uniform float uEmissiveIntensity;

void main() {
  vec3 viewDir = normalize(cameraPosition - vWorldPosition);
  float fresnel = pow(1.0 - dot(viewDir, vNormal), 3.0);

  vec3 color = uCoreColor;

  // State-based emissive
  float emissive = uEmissiveIntensity;
  if (uState == 2.0) { // speaking - pulse with bass
    float pulse = sin(uTime * 4.0 + uPulsePhase) * 0.5 + 0.5;
    emissive += pulse * uBass * 0.4;
  } else if (uState == 4.0) { // error - fast red pulse
    float pulse = sin(uTime * 8.0) * 0.5 + 0.5;
    emissive = 0.6 + pulse * 0.4;
  }

  // Fresnel glow
  color += uGlowColor * (fresnel * 0.8 + emissive * 0.4);

  float alpha = 0.9;
  if (uState == 5.0) alpha = 0.6; // muted - more transparent

  gl_FragColor = vec4(color, alpha);
}