// particleFieldFragment.glsl — Particle Field Fragment Shader
// Simple radial gradient particles with additive blending

varying float vOpacity;
varying vec3 vColor;
varying float vParticleSize;
varying float vDistFromCenter;

void main() {
  // Circular particle with soft edge
  vec2 centered = gl_PointCoord - 0.5;
  float dist = length(centered) * 2.0; // 0 at center, 1 at edge

  // Soft circular falloff
  float alpha = 1.0 - smoothstep(0.3, 1.0, dist);
  alpha *= vOpacity;

  // Add subtle glow at center
  float glow = pow(1.0 - dist, 3.0) * 0.5;
  alpha += glow * vOpacity;

  // Final color with additive blending (handled by material settings)
  vec3 finalColor = vColor * (1.0 + glow * 0.5);

  gl_FragColor = vec4(finalColor, alpha);
}